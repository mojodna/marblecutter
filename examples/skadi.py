# noqa
# coding=utf-8
from __future__ import print_function

import logging

from marblecutter import skadi
from marblecutter.sources import PostGISAdapter

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    tile = "N38W123"
    (headers, data) = skadi.render_tile(tile, PostGISAdapter())

    print("Headers: ", headers)

    with open("tmp/{}.hgt.gz".format(tile), "w") as f:
        f.write(data)
