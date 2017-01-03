#!/usr/bin/env python
# coding=utf-8

from __future__ import print_function

import math
import os
import sys

import rasterio
from rasterio.warp import (calculate_default_transform)


def get_zoom_offset(width, height, approximate_zoom):
    return len([x for x in range(approximate_zoom)
                if (height / (2 ** (x + 1))) >= 1 and (width / (2 ** (x + 1))) >= 1])


def get_zoom(input):
    input = input.replace("s3://", "/vsicurl/http://s3.amazonaws.com/")
    with rasterio.drivers():
        with rasterio.open(input) as src:
            # grab the lowest resolution dimension (assuming units are meters)
            # TODO if units aren't meters (CRS = epsg:4326), deal
            resolution = max((src.bounds.right - src.bounds.left) / src.width, (src.bounds.top - src.bounds.bottom) / src.height)

            return int(math.ceil(math.log((2 * math.pi * 6378137) /
                                          (resolution * 256)) / math.log(2)))

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
