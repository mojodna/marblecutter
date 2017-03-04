#!/usr/bin/env python
# coding=utf-8

from __future__ import print_function

import math
import os
import re
import sys

from haversine import haversine
import rasterio
from rasterio.warp import transform_bounds


def get_zoom_offset(width, height, approximate_zoom):
    return len([x for x in range(approximate_zoom)
                if (height / (2 ** (x + 1))) >= 1 and (width / (2 ** (x + 1))) >= 1])


def get_zoom(input):
    with rasterio.Env():
        with rasterio.open(input) as src:
            # grab the lowest resolution dimension
            if src.crs.is_geographic:
                left = (src.bounds[0], (src.bounds[1] + src.bounds[3]) / 2)
                right = (src.bounds[2], (src.bounds[1] + src.bounds[3]) / 2)
                top = ((src.bounds[0] + src.bounds[2]) / 2, src.bounds[3])
                bottom = ((src.bounds[0] + src.bounds[2]) / 2, src.bounds[1])

                resolution = max(haversine(left, right) * 1000 / src.width, haversine(top, bottom) * 1000 / src.height)
            else:
                resolution = max((src.bounds.right - src.bounds.left) / src.width, (src.bounds.top - src.bounds.bottom) / src.height)

            return min(22, int(math.ceil(math.log((2 * math.pi * 6378137) /
                                                  (resolution * 256)) / math.log(2))))


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("usage: {} <input>".format(os.path.basename(sys.argv[0])), file=sys.stderr)
        exit(1)

    input = sys.argv[1]
    try:
        print(get_zoom(input))
    except IOError:
        print("Unable to open '{}'.".format(input), file=sys.stderr)
        exit(1)
