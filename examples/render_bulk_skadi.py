# noqa
# coding=utf-8
from __future__ import print_function

import logging
import multiprocessing
from multiprocessing.dummy import Pool

from marblecutter import skadi

logging.basicConfig(level=logging.INFO)

POOL = Pool(multiprocessing.cpu_count() * 4)


def render_tile(tile):
    (headers, data) = skadi.render_tile(tile)

    print("Headers: ", headers)

    with open("tmp/{}.hgt.gz".format(tile), "w") as f:
        f.write(data)


def queue_tile(tile):
    print(tile)
    POOL.apply_async(render_tile, args=[tile])


if __name__ == "__main__":
    # NOTE this will generate some invalid tile names. GDAL's SRTMHGT will
    # prevent them from actually being created thought
    for ns in ("N", "S"):
        for lat in range(1):
            # for lat in range(90):
            for ew in ("E", "W"):
                for lon in range(1):
                    # for lon in range(180):
                    tile = "{}{:02d}{}{:03d}".format(ns, lat, ew, lon)
                    queue_tile(tile)

    POOL.close()
    POOL.join()
