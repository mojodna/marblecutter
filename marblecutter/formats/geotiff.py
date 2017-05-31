# noqa
# coding=utf-8
from __future__ import absolute_import

import numpy as np
from rasterio import transform
from rasterio.io import MemoryFile

CONTENT_TYPE = "image/tiff"


def format():
    def _format((data, (data_bounds, data_crs)), data_format):
        if data_format is not "raw":
            raise Exception("raw data is required")

        (count, height, width) = data.shape

        if np.issubdtype(data.dtype, np.float):
            info = np.finfo(data.dtype)
            predictor = 3
        else:
            info = np.iinfo(data.dtype)
            predictor = 2

        meta = {
            "blockxsize": 512 if width >= 512 else width,
            "blockysize": 512 if height >= 512 else height,
            "compress": "deflate",
            "count": count,
            "crs": data_crs,
            "dtype": data.dtype,
            "driver": "GTiff",
            "nodata": data.fill_value if data.dtype != np.uint8 else None,
            "predictor": predictor,
            "height": height,
            "width": width,
            "tiled": width >= 512 and height >= 512,
            "transform": transform.from_bounds(
                *data_bounds,
                width=width,
                height=height),
        }

        with MemoryFile() as memfile:
            with memfile.open(**meta) as dataset:
                # TODO not true for aerial imagery
                dataset.update_tags(AREA_OR_POINT="Point")
                dataset.write(data.filled())

            return (CONTENT_TYPE, memfile.read())

    return _format
