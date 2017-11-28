# coding=utf-8
import argparse
import botocore
import boto3
import datetime
import hashlib
import logging
import mercantile
import os
import pytz
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


# Don't copy tiles that exist and are newer than this cutoff datetime
# in yyyy-mm-ddThh:mm:ss format (in UTC)
CUTOFF_DATE = pytz.UTC.localize(datetime.datetime.strptime(
    os.environ.get('CUTOFF_DATE'),
    '%Y-%m-%dT%H:%M:%S'
)) if os.environ.get('CUTOFF_DATE') else None
# Only copy these tile types
ONLY_COPY = os.environ.get('ONLY_COPY').split(',') if os.environ.get('ONLY_COPY') else None
# The number of threads in the pool communicating with AWS
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


def head_object(s3, bucket, key):
    """ Head the given object and return the result if it exists.
    Returns `None` if it doesn't exist. """

    try:
        return s3.head_object(
            Bucket=bucket,
            Key=key,
        )
    except botocore.exceptions.ClientError as e:
        # If a client error is thrown, then check that it was a 404 error.
        # If it was a 404 error, then the object does not exist.
        error_code = int(e.response['Error']['Code'])
        if error_code == 404:
            return None
        raise


def copy_tile(tile, remove_hash, from_s3, to_s3):
    from_bucket, from_prefix = from_s3
    to_bucket, to_prefix = to_s3

    s3 = THREAD_LOCAL.s3_client

    for (type, ext) in RENDER_COMBINATIONS:
        from_key = s3_key(from_prefix, type, tile, ext, remove_hash)
        to_key = s3_key(to_prefix, type, tile, ext, False)

        if ONLY_COPY and type not in ONLY_COPY:
            logger.debug(
                'Skipping copy to s3://%s/%s because '
                'type %s not in %s',
                to_bucket, to_key,
                type, ONLY_COPY,
            )
            continue

        tries = 0
        wait = 1.0
        while True:
            try:
                tries += 1

                if CUTOFF_DATE:
                    # Check if the tile that we're copying to already exists
                    # and if its newer than the specified cutoff date
                    obj_head_resp = head_object(s3, to_bucket, to_key)
                    if obj_head_resp and obj_head_resp['LastModified'] >= CUTOFF_DATE:
                        logger.debug(
                            'Skipping copy to s3://%s/%s because '
                            'last modified %s >= %s',
                            to_bucket, to_key,
                            obj_head_resp['LastModified'].isoformat(),
                            CUTOFF_DATE.isoformat(),
                        )

                        # This is a break (instead of a return) so that we
                        # continue with the outer for loop
                        break

                s3.copy_object(
                    Bucket=to_bucket,
                    Key=to_key,
                    CopySource={
                        'Bucket': from_bucket,
                        'Key': from_key,
                    }
                )

                logger.debug(
                    "Copied s3://%s/%s to s3://%s/%s at try %s",
                    from_bucket, from_key,
                    to_bucket, to_key,
                    tries,
                )

                break
            except botocore.vendored.requests.exceptions.ConnectionError as e:
                logger.info(
                    "%s received, try %s, while copying "
                    "s3://%s/%s to s3://%s/%s, waiting %0.1f sec",
                    e, tries,
                    from_bucket, from_key,
                    to_bucket, to_key,
                    wait,
                )
                time.sleep(wait)
                wait = min(30.0, wait * 2.0)
            except botocore.exceptions.CredentialRetrievalError as e:
                logger.info(
                    "%s received, try %s, while copying "
                    "s3://%s/%s to s3://%s/%s, waiting %0.1f sec",
                    e, tries,
                    from_bucket, from_key,
                    to_bucket, to_key,
                    wait,
                )
                time.sleep(wait)
                wait = min(30.0, wait * 2.0)
            except botocore.exceptions.ClientError as e:
                error_code = str(e.response.get('Error', {}).get('Code'))
                if error_code in ('SlowDown', '503'):
                    logger.info(
                        "%s received, try %s, while copying "
                        "s3://%s/%s to s3://%s/%s, waiting %0.1f sec",
                        error_code, tries,
                        from_bucket, from_key,
                        to_bucket, to_key,
                        wait,
                    )
                    time.sleep(wait)
                    wait = min(30.0, wait * 2.0)
                elif error_code == 'NoSuchKey':
                    logger.warn(
                        "NoSuchKey received while copying "
                        "s3://%s/%s to s3://%s/%s (skipping copy)",
                        from_bucket, from_key,
                        to_bucket, to_key,
                    )
                    break
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
                root, args.max_zoom, args.from_bucket, args.from_prefix or '',
                args.to_bucket, args.to_prefix or '')

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
