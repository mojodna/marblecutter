# noqa
# coding=utf-8
from __future__ import print_function

import argparse
import boto3
import logging
import multiprocessing
from multiprocessing.dummy import Pool

import mercantile
from mercantile import Tile

from marblecutter import tiling
from marblecutter.formats import PNG, GeoTIFF
from marblecutter.transformations import Normal, Terrarium

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('batchtiler')

MAX_ZOOM = 14
POOL = Pool(multiprocessing.cpu_count() * 4)

GEOTIFF_FORMAT = GeoTIFF()
PNG_FORMAT = PNG()
NORMAL_TRANSFORMATION = Normal()
TERRARIUM_TRANSFORMATION = Terrarium()


def write_to_s3(bucket, key_prefix, tile, tile_type, data, key_suffix,
                content_type):
    s3 = boto3.resource('s3')
    key = '{}/{}/{}/{}{}'.format(
        tile_type,
        tile.zoom,
        tile.x,
        tile.y,
        key_suffix,
    )

    if key_prefix:
        key = '{}/{}'.format(key_prefix, key)

    s3.Bucket(bucket).put_object(
        Key=key,
        Body=data,
        ContentType=content_type,
    )

    logger.info('Wrote %s tile (%s bytes) to s3://%s/%s',
                tile_type, len(data), bucket, key)


def render_tile(tile, s3_details):
    s3_bucket, s3_key_prefix = s3_details

    for (type, transformation) in (("normal", NORMAL_TRANSFORMATION),
                                   ("terrarium", TERRARIUM_TRANSFORMATION)):
        (content_type, data) = tiling.render_tile(
            tile, format=PNG_FORMAT, transformation=transformation)

        write_to_s3(s3_bucket, s3_key_prefix,
                    tile, type, data,
                    '.png', content_type)

    (content_type, data) = tiling.render_tile(
        tile, format=GEOTIFF_FORMAT, scale=2)

    write_to_s3(s3_bucket, s3_key_prefix,
                tile, 'geotiff', data,
                '.tif', content_type)


def queue_tile(tile, s3_details):
    queue_render(tile, s3_details)

    if tile.z < MAX_ZOOM:
        for child in mercantile.children(tile):
            queue_tile(child, s3_details)


def queue_render(tile, s3_details):
    logger.info('Enqueueing render for tile %s', tile)
    POOL.apply_async(
        render_tile,
        args=[tile, s3_details])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('x', type=int)
    parser.add_argument('y', type=int)
    parser.add_argument('zoom', type=int)
    parser.add_argument('bucket')
    parser.add_argument('key_prefix')

    args = parser.parse_args()

    root = Tile(args.x, args.y, args.zoom)
    queue_tile(root, (args.bucket, args.key_prefix))

    POOL.close()
    POOL.join()
    logger.info('Done processing root pyramid %s', root)
