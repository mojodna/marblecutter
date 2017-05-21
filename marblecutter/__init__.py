# noqa
# coding=utf-8
from __future__ import absolute_import

import math
import multiprocessing

from affine import Affine
from cachetools.func import lru_cache
from haversine import haversine
import numpy as np
import rasterio
from rasterio import warp
from rasterio import windows
from rasterio.warp import Resampling

from . import mosaic


def _mask(data, nodata):
    if np.issubdtype(data.dtype, float):
        return np.ma.masked_values(data, nodata, copy=False)

    return np.ma.masked_equal(data, nodata, copy=False)


def _nodata(dtype):
    if np.issubdtype(dtype, int):
        return np.iinfo(dtype).min
    else:
        return np.finfo(dtype).min


def get_resolution((bounds, crs), (height, width)):
    return ((bounds[2] - bounds[0]) / width, (bounds[3] - bounds[1]) / height)


def get_resolution_in_meters((bounds, crs), (height, width)):
    # grab the lowest resolution dimension
    if crs.is_geographic:
        left = (bounds[0], (bounds[1] + bounds[3]) / 2)
        right = (bounds[2], (bounds[1] + bounds[3]) / 2)
        top = ((bounds[0] + bounds[2]) / 2, bounds[3])
        bottom = ((bounds[0] + bounds[2]) / 2, bounds[1])

        return (haversine(left, right) * 1000 / width, haversine(top, bottom) * 1000 / height)

    return ((bounds[2] - bounds[0]) / width, (bounds[3] - bounds[1]) / height)


@lru_cache(maxsize=1024)
def get_source(path):
    """Cached source opening."""
    with rasterio.Env(CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.vrt,.tif,.ovr,.msk'):
        return rasterio.open(path)


def get_zoom(resolution):
    return min(22, int(round(math.log((2 * math.pi * 6378137) /
                                          (resolution * 256)) / math.log(2))))


def read_window(src, (bounds, bounds_crs), (height, width)):
    # NOTE: this produces slightly different horizontal pixel sizes than reading
    # windows from a warped VRT
    ((left, right), (bottom, top)) = warp.transform(bounds_crs, src.crs, bounds[::2], bounds[1::2])
    bounds_src = (left, bottom, right, top)
    window = windows.from_bounds(*bounds_src, transform=src.transform, boundless=True)

    # scaling factor
    scale = Affine.scale(max(1, window.num_cols / width),
                         max(1, window.num_rows / height))

    # crop the data window to available data
    window_src = windows.crop(window, height=src.height, width=src.width)
    window_size = (window_src.num_cols, window_src.num_rows)

    # target shape, scaled
    target_shape = tuple(reversed(map(int, map(math.floor, window_size * ~scale))))

    # read data
    data = src.read(
        out_shape=(src.count, ) + target_shape,
        window=window_src,
    )

    if src.nodata is not None:
        # TODO test this with NED 1/9
        # some datasets use the min value but report an alternate nodata value
        # mask = np.where((data == src.nodata) | (data == _nodata(data.dtype)), True, False)
        data = _mask(data, src.nodata)
    else:
        data = np.ma.masked_array(data, mask=False)

    data = data.astype(np.float32)

    window_bounds = windows.bounds(window_src, src.transform)

    return (data, (window_bounds, src.crs))


def render((bounds, bounds_crs), shape, target_crs, format, transformation=None, buffer=0):
    """Render data intersecting bounds into shape using an optional transformation."""
    resolution = get_resolution((bounds, bounds_crs), shape)
    resolution_m = get_resolution_in_meters((bounds, bounds_crs), shape)

    # apply buffer
    shape = map(lambda dim: dim + (2 * buffer), shape)
    bounds = map(lambda (i, p): p - (buffer * resolution[i % 2]) if i < 2 else p + (buffer * resolution[i % 2]), enumerate(bounds))

    sources = mosaic.get_sources(bounds, resolution_m)

    (data, (data_bounds, data_crs)) = mosaic.composite(sources, (bounds, bounds_crs), shape, target_crs)

    data_format = "raw"

    if transformation:
        (data, data_format) = apply_transformation(transformation)

    buffered = False
    if buffered:
        # TODO figure out args
        data = crop()

    return format((data, (data_bounds, data_crs)), data_format)
