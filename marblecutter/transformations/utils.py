# coding=utf-8
from __future__ import absolute_import

import numpy as np
from rasterio import warp
from rasterio.crs import CRS

WGS84_CRS = CRS.from_epsg(4326)


def apply_latitude_adjustments(data, (bounds, crs)):
    (_, height, width) = data.shape

    ys = np.interp(
        np.arange(height), [0, height - 1], [bounds[3], bounds[1]])
    xs = np.empty_like(ys)
    xs.fill(bounds[0])

    longitudes, latitudes = warp.transform(crs, WGS84_CRS, xs, ys)

    factors = 1 / np.cos(np.radians(latitudes))

    # convert to 2d array, rotate 270º, scale data
    return data * np.rot90(np.atleast_2d(factors), 3)
