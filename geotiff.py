# coding=utf-8
from __future__ import division

import logging

import mercantile
import numpy as np
import rasterio
from rasterio import transform
from rasterio.crs import CRS
from rasterio.io import MemoryFile

BUFFER = 4
LOG = logging.getLogger(__name__)
SCALE = 2 # always generate 512x512 files

WEB_MERCATOR_CRS = CRS({'init': 'epsg:3857'})


def render(tile, (data, buffers)):
    (count, width, height) = data.shape

    if np.issubdtype(data.dtype, np.float):
        info = np.finfo(data.dtype)
        predictor = 3
    else:
        info = np.iinfo(data.dtype)
        predictor = 2

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
        'transform': transform.from_bounds(*mercantile.bounds(tile), width=width, height=height),
    }

    with MemoryFile() as memfile:
        with memfile.open(**meta) as dataset:
            dataset.write(data[:,
                               buffers[0]:data.shape[0] - buffers[2],
                               buffers[1]:data.shape[1] - buffers[3]])

        return ('image/tiff', memfile.read())
