# noqa
# coding=utf-8
from __future__ import print_function

import argparse
import logging
import os
import time
from functools import wraps
from multiprocessing.dummy import Pool

from shapely import wkb
from shapely.geometry import box

import boto3
import botocore
import mercantile
import psycopg2
import psycopg2.extras
from marblecutter import tiling
from marblecutter.formats import PNG, GeoTIFF
from marblecutter.sources import MemoryAdapter
from marblecutter.stats import Timer
from marblecutter.transformations import Normal, Terrarium
from mercantile import Tile

logging.basicConfig(level=logging.INFO)
# Quieting boto messages down a little
logging.getLogger('boto3.resources.action').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('marblecutter').setLevel(logging.WARNING)
logging.getLogger('marblecutter.mosaic').setLevel(logging.WARNING)
logging.getLogger('marblecutter.sources').setLevel(logging.WARNING)
logger = logging.getLogger('batchtiler')

POOL_SIZE = 12
POOL = Pool(POOL_SIZE)

GEOTIFF_FORMAT = GeoTIFF()
PNG_FORMAT = PNG()
NORMAL_TRANSFORMATION = Normal()
TERRARIUM_TRANSFORMATION = Terrarium()

RENDER_COMBINATIONS = [
    ("normal", NORMAL_TRANSFORMATION, PNG_FORMAT, ".png"),
    ("terrarium", TERRARIUM_TRANSFORMATION, PNG_FORMAT, ".png"),
    ("geotiff", None, GEOTIFF_FORMAT, ".tif"),
]


# From https://www.saltycrane.com/blog/2009/11/trying-out-retry-decorator-python/
def retry(ExceptionToCheck,
          tries=4,
          delay=3,
          backoff=2,
          max_delay=60,
          logger=None):
    def deco_retry(f):
        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except ExceptionToCheck, e:
                    msg = "%s, Retrying in %d seconds..." % (str(e), mdelay)
                    if logger:
                        logger.exception(msg)
                    else:
                        print(msg)
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
                    mdelay = min(mdelay, max_delay)
            return f(*args, **kwargs)

        return f_retry  # true decorator

    return deco_retry


def s3_key(tile_type, tile, key_suffix, key_prefix):
    key = '{}/{}/{}/{}{}'.format(
        tile_type,
        tile.z,
        tile.x,
        tile.y,
        key_suffix,
    )

    if key_prefix:
        key = '{}/{}'.format(key_prefix, key)

    return key


@retry(botocore.exceptions.ClientError, tries=30, logger=logger)
def write_to_s3(obj,
                tile,
                tile_type,
                data,
                key_suffix,
                headers):

    obj.put(
        Body=data,
        ContentType=headers['Content-Type'],
        Metadata={k: headers[k]
                  for k in headers if k != 'Content-Type'})

    return obj


def build_source_index(tile, min_zoom, max_zoom):
    source_cache = MemoryAdapter()
    bbox = box(*mercantile.bounds(tile))

    database_url = os.environ.get('DATABASE_URL')

    with psycopg2.connect(database_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT
                    filename, resolution, source, url,
                    min_zoom, max_zoom, priority, approximate_zoom,
                    wkb_geometry
                FROM
                    footprints
                WHERE
                    ST_Intersects(
                        wkb_geometry,
                        ST_GeomFromText(%s, 4326)
                    )
                    AND min_zoom >= %s
                    AND max_zoom <= %s
                    AND enabled = true
                """, (bbox.to_wkt(), min_zoom, max_zoom))

            for row in cur:
                row = dict(row)
                shape = wkb.loads(row.pop('wkb_geometry').decode('hex'))
                source_cache.add_source(shape, row)

    return source_cache


def render_tile_exc_wrapper(tile, s3_details, sources):
    try:
        render_tile_and_put_to_s3(tile, s3_details, sources)
    except Exception:
        logger.exception('Error while processing tile %s', tile)
        raise


def s3_obj_exists(obj):
    try:
        obj.load()
        return True
    except botocore.exceptions.ClientError, e:
        error_code = int(e.response['Error']['Code'])
        if error_code == 404:
            return False
        raise


@retry((psycopg2.OperationalError, ), logger=logger)
def render_tile(tile, format, transformation, sources):
    return tiling.render_tile(
        tile, sources, format=format, transformation=transformation)


def render_tile_and_put_to_s3(tile, s3_details, sources):
    s3_bucket, s3_key_prefix = s3_details
    # Each thread needs its own boto3 Session object – it's not threadsafe
    session = boto3.session.Session()
    s3 = session.resource('s3')

    for (type, transformation, format, ext) in RENDER_COMBINATIONS:
        key = s3_key()
        obj = s3.Object(s3_bucket, key)
        if s3_obj_exists(obj):
            logger.debug(
                '(%02d/%06d/%06d) Skipping existing %s tile',
                tile.z, tile.x, tile.y, type,
            )
            continue

        with Timer() as t:
            (headers, data) = render_tile(
                tile, format, transformation, sources)

        logger.debug(
            '(%02d/%06d/%06d) Took %0.3fs to render %s tile (%s bytes), Source: %s, Timers: %s',
            tile.z, tile.x, tile.y, t.elapsed, type,
            len(data),
            headers.get('X-Imagery-Sources'),
            headers.get('X-Timers'),
        )

        with Timer() as t:
            obj = write_to_s3(obj, tile, type, data, ext, headers)

        logger.debug(
            '(%02d/%06d/%06d) Took %0.3fs to write %s tile to s3://%s/%s',
            tile.z, tile.x, tile.y, t.elapsed, type,
            obj.bucket_name, obj.key,
        )


def queue_tile(tile, max_zoom, s3_details, sources):
    queue_render(tile, s3_details, sources)

    if tile.z < max_zoom:
        for child in mercantile.children(tile):
            queue_tile(child, max_zoom, s3_details, sources)


def queue_render(tile, s3_details, sources):
    logger.debug('Enqueueing render for tile %s', tile)
    POOL.apply_async(render_tile_exc_wrapper, args=[tile, s3_details, sources])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('x', type=int)
    parser.add_argument('y', type=int)
    parser.add_argument('zoom', type=int)
    parser.add_argument('max_zoom', type=int)
    parser.add_argument('bucket')
    parser.add_argument('--key_prefix')

    args = parser.parse_args()
    root = Tile(args.x, args.y, args.zoom)

    logger.info('Caching sources for root tile %s to zoom %s',
                root, args.max_zoom)

    source_index = build_source_index(root, args.zoom, args.min_zoom)

    logger.info('Running %s processes', POOL_SIZE)

    queue_tile(root, args.max_zoom, (args.bucket, args.key_prefix),
               source_index)

    POOL.close()
    POOL.join()
    logger.info('Done processing root pyramid %s to zoom %s',
                root, args.max_zoom)
