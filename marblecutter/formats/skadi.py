# noqa
# coding=utf-8
from __future__ import absolute_import

from gzip import GzipFile
from io import BytesIO

import numpy as np
from rasterio import transform
from rasterio.io import MemoryFile

from .. import _nodata

CONTENT_TYPE = "application/gzip"


def format():
    def _format((data, (data_bounds, data_crs)), data_format):
        if data_format is not "raw":
            raise Exception("raw data is required")

        (count, height, width) = data.shape

        # HGT only supports byte, int16, and uint16
        data = data.astype(np.int16)
        data.fill_value = _nodata(np.int16)

        meta = {
            "count": count,
            "crs": data_crs,
            "dtype": data.dtype,
            "driver": "SRTMHGT",
            "nodata": data.fill_value,
            "height": height,
            "width": width,
            "transform": transform.from_bounds(
                *data_bounds,
                width=width,
                height=height),
        }

        # GDAL's SRTMHGT driver requires that filenames be correct
        (lon, lat) = map(int, map(round, data_bounds[:2]))
        x = "W" if lon < 0 else "E"
        y = "S" if lat < 0 else "N"
        filename = "{}{}{}{}.hgt".format(y, abs(lat), x, abs(lon))
        filename = "{}{:02d}{}{:03d}.hgt".format(y, abs(lat), x, abs(lon))

        with MemoryFile(filename=filename) as memfile:
            with memfile.open(**meta) as dataset:
                dataset.write(data.filled())

            out = BytesIO()
            with GzipFile(mode='wb', fileobj=out) as f:
                f.write(memfile.read())

        return (CONTENT_TYPE, out.getvalue())

    return _format
