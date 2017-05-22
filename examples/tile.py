# noqa
# coding=utf-8
from __future__ import print_function

import logging

from marblecutter import tiling
from marblecutter.formats import GeoTIFF
from mercantile import Tile

logging.basicConfig(level=logging.INFO)


if __name__ == "__main__":
    tile = Tile(324, 787, 11)
    (content_type, data) = tiling.render_tile(tile, format=GeoTIFF(), scale=2)

    print("Content-type: ", content_type)

    with open("tmp/11_324_787.tif", "w") as f:
        f.write(data)
