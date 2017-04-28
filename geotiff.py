# noqa
# coding=utf-8
from __future__ import division

import logging

import mercantile
import numpy as np
from rasterio import transform
from rasterio.crs import CRS
from rasterio.io import MemoryFile

BUFFER = 0
CONTENT_TYPE = 'image/tiff'
EXT = 'tif'
LOG = logging.getLogger(__name__)
NAME = 'GeoTIFF'
SCALE = 2  # always generate 512x512 files

WEB_MERCATOR_CRS = CRS({'init': 'epsg:3857'})


def render(tile, (data, buffers)): # noqa
    (count, width, height) = data.shape
    width -= buffers[0] + buffers[2]
    height -= buffers[1] + buffers[3]

    if np.issubdtype(data.dtype, np.float):
        info = np.finfo(data.dtype)
        predictor = 3
    else:
        info = np.iinfo(data.dtype)
        predictor = 2

    bounds = mercantile.bounds(tile)
    m_bounds = mercantile.xy(*bounds[0:2]) + mercantile.xy(*bounds[2:4])

    # use the min value unless it's 0, in which case use the max
    nodata = info.min or info.max

    meta = {
        'blockxsize': 256,
        'blockysize': 256,
        'compress': 'deflate',
        'count': count,
        'crs': WEB_MERCATOR_CRS,
        'dtype': data.dtype,
        'driver': 'GTiff',
        'nodata': nodata,
        'predictor': predictor,
        'height': height,
        'width': width,
        'tiled': True,
        'transform': transform.from_bounds(
            *m_bounds,
            width=width,
            height=height),
    }

    with MemoryFile() as memfile:
        with memfile.open(**meta) as dataset:
            dataset.write(data[:,
                               buffers[3]:data.shape[1] - buffers[1],
                               buffers[0]:data.shape[2] - buffers[2]])

        return (CONTENT_TYPE, memfile.read())
