# noqa
# coding=utf-8
from __future__ import print_function

import logging

from marblecutter import tiling
from marblecutter.transformations import Hillshade
from marblecutter.formats import ColorRamp, GeoTIFF
from mercantile import Tile

logging.basicConfig(level=logging.INFO)


if __name__ == "__main__":
    tile = Tile(1308, 3164, 13)

    hillshade = Hillshade(resample=True, add_slopeshade=True)
    (content_type, data) = tiling.render_tile(
        tile, format=GeoTIFF(), transformation=hillshade, scale=1)

    print("Content-type: ", content_type)

    with open("tmp/{}_{}_{}_hillshade.tif".format(
                tile.z, tile.x, tile.y), "w") as f:
        f.write(data)

    (content_type, data) = tiling.render_tile(tile, format=GeoTIFF())

    print("Content-type: ", content_type)

    with open("tmp/{}_{}_{}.tif".format(tile.z, tile.x, tile.y), "w") as f:
        f.write(data)

    # tile = Tile(654, 1582, 12)
    (content_type, data) = tiling.render_tile(
        tile, format=ColorRamp("png"), transformation=hillshade, scale=2)

    print("Content-type: ", content_type)

    with open("tmp/{}_{}_{}_hillshade.png".format(
                tile.z, tile.x, tile.y), "w") as f:
        f.write(data)
