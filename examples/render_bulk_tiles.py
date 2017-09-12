# coding=utf-8
from __future__ import print_function

import argparse
import boto3
import botocore
import logging
import re
import time
from functools import wraps
from multiprocessing.dummy import Pool

from marblecutter import tiling
from marblecutter.formats import PNG, GeoTIFF
from marblecutter.sources import PostGISAdapter
from marblecutter.stats import Timer
from marblecutter.transformations import Normal, Terrarium
from mercantile import Tile

logging.basicConfig(level=logging.INFO)
# Quieting boto messages down a little
logging.getLogger('boto3.resources.action').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('marblecutter.mosaic').setLevel(logging.WARNING)
logging.getLogger('marblecutter.sources').setLevel(logging.WARNING)
logger = logging.getLogger('batchtiler')

POOL = Pool(12)
CATALOG = PostGISAdapter()

GEOTIFF_FORMAT = GeoTIFF()
PNG_FORMAT = PNG()
NORMAL_TRANSFORMATION = Normal()
TERRARIUM_TRANSFORMATION = Terrarium()
TILE_RE = re.compile(r'(\w*)/(\d+)/(\d+)/(\d+)\.(\w+)')

RENDER_COMBINATIONS = {
    "normal": (NORMAL_TRANSFORMATION, PNG_FORMAT, ".png"),
    "terrarium": (TERRARIUM_TRANSFORMATION, PNG_FORMAT, ".png"),
    "geotiff": (None, GEOTIFF_FORMAT, ".tif"),
}


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


@retry(botocore.exceptions.ClientError, tries=30, logger=logger)
def write_to_s3(bucket, key,
                data, headers, overwrite=False):

    content_type = headers.pop('Content-Type')

    obj = bucket.Object(key)
    if overwrite:
        obj.put(
            Body=data,
            ContentType=content_type,
            Metadata={k: headers[k]
                      for k in headers})
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
                    ContentType=content_type,
                    Metadata={
                        k: headers[k]
                        for k in headers
                    })

    return obj


def render_tile_and_put_to_s3(tile_str, s3_bucket, key_prefix):
    m = TILE_RE.match(tile_str)
    tile = Tile(int(m.group(3)), int(m.group(4)), int(m.group(2)))
    tile_type = m.group(1)
    render_data = RENDER_COMBINATIONS.get(tile_type)

    if not render_data:
        logger.error("Could not parse tile string %s", tile_str)

    (transformation, format, suffix) = render_data
    key = "{}/{}/{}/{}{}".format(
        tile_type,
        tile.z,
        tile.x,
        tile.y,
        suffix,
    )

    if key_prefix:
        key = key_prefix + '/' + key

    with Timer() as t:
        (headers, data) = tiling.render_tile(
            tile, CATALOG, format=format, transformation=transformation)
    logger.debug("Tile %s rendered in %0.3f", tile, t.elapsed)

    with Timer() as t:
        # Each thread needs its own boto3 Session object – it's not threadsafe
        session = boto3.session.Session()
        s3 = session.resource('s3')
        bucket = s3.Bucket(s3_bucket)

        obj = write_to_s3(bucket, key, data, headers, overwrite=True)
    logger.debug("Tile %s uploaded to s3://%s/%s in %0.3f",
                 tile, obj.bucket_name, obj.key, t.elapsed)


def render_tile_exc_wrapper(tile, s3_bucket, key_prefix):
    try:
        render_tile_and_put_to_s3(tile, s3_bucket, key_prefix)
    except Exception:
        logger.exception('Error while processing tile %s', tile)
        raise


def queue_tile(tile, bucket, key_prefix):
    POOL.apply_async(render_tile_exc_wrapper, args=[tile, bucket, key_prefix])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('bucket')
    parser.add_argument('tiles', nargs='+')
    parser.add_argument('--prefix')
    args = parser.parse_args()

    logger.info("Writing %s tiles to S3 bucket %s with prefix '%s'",
                len(args.tiles), args.bucket, args.prefix)

    for tile in args.tiles:
        queue_tile(tile, args.bucket, args.prefix)

    POOL.close()
    POOL.join()
    logger.info("Done.")
