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
logging.getLogger('marblecutter.mosaic').setLevel(logging.WARNING)
logger = logging.getLogger('batchtiler')

MAX_ZOOM = 15
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


@retry((Exception, ), tries=30, logger=logger)
def write_to_s3(bucket,
                key_prefix,
                tile,
                tile_type,
                data,
                key_suffix,
                headers,
                overwrite=False):
    key = '{}/{}/{}/{}{}'.format(
        tile_type,
        tile.z,
        tile.x,
        tile.y,
        key_suffix, )

    if key_prefix:
        key = '{}/{}'.format(key_prefix, key)

    obj = bucket.Object(key)
    if overwrite:
        obj.put(
            Body=data,
            ContentType=headers['Content-Type'],
            Metadata={k: headers[k]
                      for k in headers if k != 'Content-Type'})
    else:
        try:
            obj.load()
        except botocore.exceptions.ClientError as e:
            # If a client error is thrown, then check that it was a 404 error.
            # If it was a 404 error, then the object does not exist.
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                obj.put(
                    Body=data,
                    ContentType=headers['Content-Type'],
                    Metadata={
                        k: headers[k]
                        for k in headers if k != 'Content-Type'
                    })

    return obj


def build_source_index(tile):
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
                    AND enabled = true
                """, (bbox.to_wkt(),))

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


@retry((psycopg2.OperationalError, ), logger=logger)
def render_tile(tile, format, transformation, sources):
    return tiling.render_tile(
        tile, sources, format=format, transformation=transformation)


def render_tile_and_put_to_s3(tile, s3_details, sources):
    s3_bucket, s3_key_prefix = s3_details
    session = boto3.session.Session()
    s3 = session.resource('s3')
    bucket = s3.Bucket(s3_bucket)

    for (type, transformation, format, ext) in RENDER_COMBINATIONS:
        with Timer() as t:
            (headers, data) = render_tile(tile, format, transformation,
                                          sources)

        logger.info(
            '(%02d/%06d/%06d) Took %0.3fs to render %s tile (%s bytes), Source: %s, Timers: %s',
            tile.z, tile.x, tile.y, t.elapsed, type,
            len(data),
            headers.get('X-Imagery-Sources'), headers.get('X-Timers'))

        with Timer() as t:
            obj = write_to_s3(bucket, s3_key_prefix, tile, type, data, ext,
                              headers)

        logger.info('(%02d/%06d/%06d) Took %0.3fs to write %s tile to '
                    's3://%s/%s', tile.z, tile.x, tile.y, t.elapsed, type,
                    obj.bucket_name, obj.key)


def queue_tile(tile, s3_details, sources):
    queue_render(tile, s3_details, sources)

    if tile.z < MAX_ZOOM:
        for child in mercantile.children(tile):
            queue_tile(child, s3_details, sources)


def queue_render(tile, s3_details, sources):
    logger.info('Enqueueing render for tile %s', tile)
    POOL.apply_async(render_tile_exc_wrapper, args=[tile, s3_details, sources])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('x', type=int)
    parser.add_argument('y', type=int)
    parser.add_argument('zoom', type=int)
    parser.add_argument('bucket')
    parser.add_argument('key_prefix')

    args = parser.parse_args()
    root = Tile(args.x, args.y, args.zoom)

    logger.info('Caching sources for root tile %s', root)

    source_index = build_source_index(root)

    logger.info('Running %s processes', POOL_SIZE)

    queue_tile(root, (args.bucket, args.key_prefix), source_index)

    POOL.close()
    POOL.join()
    logger.info('Done processing root pyramid %s', root)
