# noqa
# coding=utf-8
from __future__ import print_function

import logging

from marblecutter import tiling
from marblecutter.transformations import Terrarium
from marblecutter.formats import PNG
from mercantile import Tile

logging.basicConfig(level=logging.INFO)


if __name__ == "__main__":
    tile = Tile(324, 787, 11)
    (headers, data) = tiling.render_tile(tile, format=PNG(), transformation=Terrarium(), scale=2)

    print("Headers: ", headers)

    with open("tmp/11_324_787_terrarium.png", "w") as f:
        f.write(data)
