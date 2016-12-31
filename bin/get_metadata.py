#!/usr/bin/env python
# coding=utf-8

from __future__ import print_function

import json
import math
import os
import sys

import rasterio
from rasterio.warp import transform_bounds

from get_zoom import get_zoom, get_zoom_offset

S3_BUCKET = os.environ["S3_BUCKET"]


def get_metadata(id):
    scene = "s3://{}/sources/{}/index.tif".format(S3_BUCKET, id)
    scene_vrt = "s3://{}/sources/{}/index.vrt".format(S3_BUCKET, id)

    with rasterio.drivers():
        with rasterio.open(scene.replace("s3://", "/vsicurl/http://s3.amazonaws.com/")) as src:
            bounds = transform_bounds(src.crs, {'init': 'epsg:4326'}, *src.bounds)
            approximate_zoom = get_zoom(scene)
            maxzoom = max(approximate_zoom + 3, 22)
            minzoom = approximate_zoom - get_zoom_offset(src.width, src.height, approximate_zoom)
            source = scene_vrt.replace("s3://", "http://s3.amazonaws.com/")

            return {
              "bounds": bounds,
              "maxzoom": maxzoom,
              "meta": {
                "approximateZoom": approximate_zoom,
                "bandCount": src.count,
                "height": src.height,
                "source": source,
                "width": src.width,
              },
              "minzoom": minzoom,
              "name": id,
              "tilejson": "2.1.0"
            }

if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("usage: {} <scene>".format(os.path.basename(sys.argv[0])), file=sys.stderr)
        exit(1)

    input = sys.argv[1]
    try:
        print(json.dumps(get_metadata(input)))
    except (IOError, rasterio._err.CPLE_HttpResponse):
        print("Unable to open '{}'.".format(input), file=sys.stderr)
        exit(1)
