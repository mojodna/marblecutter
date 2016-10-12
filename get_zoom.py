import math
import sys

import rasterio
from rasterio.warp import (calculate_default_transform)


CHUNK_SIZE = 256


def get_zoom(input, dst_crs="EPSG:3857"):
    input = input.replace("s3://", "/vsicurl/http://s3.amazonaws.com/")
    with rasterio.drivers():
        with rasterio.open(input) as src:
            affine, _, _ = calculate_default_transform(src.crs, dst_crs,
                src.width, src.height, *src.bounds, resolution=None)

            # grab the lowest resolution dimension
            resolution = max(abs(affine[0]), abs(affine[4]))

            return int(math.ceil(math.log((2 * math.pi * 6378137) /
                                          (resolution * CHUNK_SIZE)) / math.log(2)))

if __name__ == "__main__":
        print(get_zoom(sys.argv[1]))
