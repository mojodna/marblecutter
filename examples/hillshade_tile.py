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
    tile = Tile(324, 787, 11)
    hillshade = Hillshade(resample=True, add_slopeshade=True)
    (content_type, data) = tiling.render_tile(tile, format=GeoTIFF(), transformation=hillshade, scale=2)

    print("Content-type: ", content_type)

    with open("tmp/11_324_787_hillshade.tif", "w") as f:
        f.write(data)

    (content_type, data) = tiling.render_tile(tile, format=ColorRamp("png"), transformation=hillshade, scale=2)

    print("Content-type: ", content_type)

    with open("tmp/11_324_787_hillshade.png", "w") as f:
        f.write(data)
