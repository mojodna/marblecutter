# noqa
# coding=utf-8
from __future__ import print_function

import logging

from marblecutter import tiling
from marblecutter.transformations import Normal
from marblecutter.formats import PNG
from mercantile import Tile

logging.basicConfig(level=logging.INFO)


if __name__ == "__main__":
    tile = Tile(324, 787, 11)
    (content_type, data) = tiling.render_tile(tile, format=PNG(), transformation=Normal(), scale=2, buffer=2)

    print("Content-type: ", content_type)

    with open("tmp/11_324_787_buffered_normal.png", "w") as f:
        f.write(data)
