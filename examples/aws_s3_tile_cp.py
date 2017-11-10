# coding=utf-8
import argparse
import botocore
import boto3
import hashlib
import logging
import mercantile
import os
import time
import threading
from mercantile import Tile
from multiprocessing.dummy import Pool


logging.basicConfig(level=logging.INFO)
# Quieting boto messages down a little
logging.getLogger('boto3.resources.action').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('marblecutter').setLevel(logging.WARNING)
logging.getLogger('marblecutter.mosaic').setLevel(logging.WARNING)
logging.getLogger('marblecutter.sources').setLevel(logging.WARNING)
logger = logging.getLogger('batchtiler')

if os.environ.get('VERBOSE'):
    logger.setLevel(logging.DEBUG)


THREAD_LOCAL = threading.local()


def initialize_thread():
    # Each thread needs its own boto3 Session object - it's not threadsafe
    THREAD_LOCAL.boto_session = boto3.session.Session()
    THREAD_LOCAL.s3_client = THREAD_LOCAL.boto_session.client('s3')


POOL_SIZE = int(os.environ.get('POOL_SIZE', '12'))
POOL = Pool(POOL_SIZE, initializer=initialize_thread)


RENDER_COMBINATIONS = [
    ("normal", ".png"),
    ("terrarium", ".png"),
    ("geotiff", ".tif"),
]


def s3_key(key_prefix, tile_type, tile, key_suffix, include_hash):
    key = '{}/{}/{}/{}{}'.format(
        tile_type,
        tile.z,
        tile.x,
        tile.y,
        key_suffix,
    )

    if include_hash:
        h = hashlib.md5(key).hexdigest()[:6]
        key = '{}/{}'.format(
            h,
            key,
        )

    if key_prefix:
        key = '{}/{}'.format(key_prefix, key)

    return key


def copy_tile(tile, remove_hash, from_s3, to_s3):
    from_bucket, from_prefix = from_s3
    to_bucket, to_prefix = to_s3

    s3 = THREAD_LOCAL.s3_client

    for (type, ext) in RENDER_COMBINATIONS:
        from_key = s3_key(from_prefix, type, tile, ext, remove_hash)
        to_key = s3_key(to_prefix, type, tile, ext, False)

        tries = 0
        wait = 1.0
        while True:
            try:
                tries += 1
                s3.copy_object(
                    Bucket=to_bucket,
                    Key=to_key,
                    CopySource={
                        'Bucket': from_bucket,
                        'Key': from_key,
                    }
                )

                logger.info(
                    "Copied s3://%s/%s to s3://%s/%s at try %s",
                    from_bucket, from_key,
                    to_bucket, to_key,
                    tries,
                )

                break
            except botocore.exceptions.ClientError as e:
                if e.response.get('Error', {}).get('Code') == 'SlowDown':
                    logger.info(
                        "SlowDown received, try %s, while copying "
                        "s3://%s/%s to s3://%s/%s, waiting %0.1f sec",
                        from_bucket, from_key,
                        to_bucket, to_key,
                        wait, tries
                    )
                    time.sleep(wait)
                    wait = min(30.0, wait * 2.0)
                else:
                    raise


def tile_exc_wrapper(tile, remove_hash, from_s3, to_s3):
    try:
        copy_tile(tile, remove_hash, from_s3, to_s3)
    except Exception:
        logger.exception('Error while processing tile %s', tile)
        raise


def queue_render(tile, remove_hash, from_s3, to_s3):
    logger.debug('Enqueueing render for tile %s', tile)
    POOL.apply_async(
        tile_exc_wrapper,
        args=[tile, remove_hash, from_s3, to_s3]
    )


def queue_tile(tile, max_zoom, remove_hash, from_s3, to_s3):
    queue_render(tile, remove_hash, from_s3, to_s3)

    if tile.z < max_zoom:
        for child in mercantile.children(tile):
            queue_tile(child, max_zoom, remove_hash, from_s3, to_s3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('x', type=int)
    parser.add_argument('y', type=int)
    parser.add_argument('zoom', type=int)
    parser.add_argument('max_zoom', type=int)
    parser.add_argument('from_bucket')
    parser.add_argument('to_bucket')
    parser.add_argument('--from_prefix')
    parser.add_argument('--to_prefix')
    parser.add_argument('--remove_hash', dest='remove_hash', action='store_true', default=False)

    args = parser.parse_args()
    root = Tile(args.x, args.y, args.zoom)

    logger.info('Copying tiles from root tile %s to zoom %s at '
                's3://%s/%s to s3://%s/%s',
                root, args.max_zoom, args.from_bucket, args.from_prefix,
                args.to_bucket, args.to_prefix)

    logger.info('Running %s processes', POOL_SIZE)

    start_time = time.time()
    queue_tile(root, args.max_zoom, args.remove_hash,
               (args.from_bucket, args.from_prefix),
               (args.to_bucket, args.to_prefix))

    est_copies = (4**(args.max_zoom - args.zoom)) * len(RENDER_COMBINATIONS)

    POOL.close()
    POOL.join()
    end_time = time.time()
    logger.info('Done processing pyramid %s to zoom %s (%d ops in %0.1f sec)',
                root, args.max_zoom, est_copies, (end_time - start_time))
