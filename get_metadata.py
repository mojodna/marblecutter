# coding=utf-8

import json
import math
import os
import sys

import rasterio
from rasterio.warp import transform_bounds

from get_zoom import get_zoom

S3_BUCKET = os.environ["S3_BUCKET"]

def get_metadata(id):
    scene = "s3://{}/sources/{}/index.tif".format(S3_BUCKET, id)
    scene_vrt = "s3://{}/sources/{}/index.vrt".format(S3_BUCKET, id)

    with rasterio.drivers():
        with rasterio.open(scene.replace("s3://", "/vsicurl/http://s3.amazonaws.com/")) as src:
            bounds = transform_bounds(src.crs, {'init': 'epsg:4326'}, *src.bounds)
            approximate_zoom = get_zoom(scene)
            maxzoom = approximate_zoom + 3
            minzoom = approximate_zoom - math.floor(math.log(max(src.width, src.height)) / math.log(2)) + 8
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
    # usage: python get_metadata.py <id>
    print(json.dumps(get_metadata(sys.argv[1])))
