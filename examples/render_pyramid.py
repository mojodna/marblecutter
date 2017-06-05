# noqa
# coding=utf-8
from __future__ import print_function

import logging
import multiprocessing
from multiprocessing.dummy import Pool

import mercantile
from mercantile import Tile

from marblecutter import tiling
from marblecutter.formats import PNG, GeoTIFF
from marblecutter.transformations import Normal, Terrarium

logging.basicConfig(level=logging.INFO)

MAX_ZOOM = 14
POOL = Pool(multiprocessing.cpu_count() * 4)

GEOTIFF_FORMAT = GeoTIFF()
PNG_FORMAT = PNG()
NORMAL_TRANSFORMATION = Normal()
TERRARIUM_TRANSFORMATION = Terrarium()


def render_tile(tile):
    for (type, transformation) in (("normal", NORMAL_TRANSFORMATION),
                                   ("terrarium", TERRARIUM_TRANSFORMATION)):
        (content_type, data) = tiling.render_tile(
            tile, format=PNG_FORMAT, transformation=transformation)

        with open(
            "tmp/{}_{}_{}_{}.png".format(
                tile.z, tile.x, tile.y, type), "w") as f:
            f.write(data)

    (content_type, data) = tiling.render_tile(
        tile, format=GEOTIFF_FORMAT, scale=2)

    with open(
        "tmp/{}_{}_{}_{}.tif".format(tile.z, tile.x, tile.y, type), "w"
    ) as f:
        f.write(data)


def queue_tile(tile):
    queue_render(tile)

    if tile.z < MAX_ZOOM:
        for child in mercantile.children(tile):
            queue_tile(child)


def queue_render(tile):
    print(tile)
    POOL.apply_async(
        render_tile,
        args=[tile])


if __name__ == "__main__":
    root = Tile(328, 793, 11)
    queue_tile(root)

    POOL.close()
    POOL.join()
