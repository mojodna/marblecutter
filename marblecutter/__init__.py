# noqa
# coding=utf-8
from __future__ import absolute_import, division, print_function

import math

from affine import Affine
from cachetools.func import lru_cache
from haversine import haversine
import numpy as np
import rasterio
from rasterio import transform
from rasterio import windows
from rasterio.crs import CRS
from rasterio.vrt import WarpedVRT
from rasterio.warp import Resampling

from . import mosaic

WEB_MERCATOR_CRS = CRS.from_epsg(3857)
WGS84_CRS = CRS.from_epsg(4326)


def _isimage(data_format):
    return data_format.upper() in ["RGB", "RGBA"]


def _mask(data, nodata):
    if np.issubdtype(data.dtype, float):
        return np.ma.masked_values(data, nodata, copy=False)

    return np.ma.masked_equal(data, nodata, copy=False)


def _nodata(dtype):
    if np.issubdtype(dtype, int):
        return np.iinfo(dtype).min
    else:
        return np.finfo(dtype).min


def crop((data, (data_bounds, data_crs)), data_format, offset):
    if _isimage(data_format):
        width, height, _ = data.shape

        data = data[offset:-offset, offset:-offset, :]

        return (data, (None, None))

    _, height, width = data.shape
    t = transform.from_bounds(*data_bounds, width=width, height=height)

    data = data[:, offset:-offset, offset:-offset]

    cropped_window = windows.Window(offset, offset, *data.shape[1:])
    data_bounds = windows.bounds(cropped_window, t)

    return (data, (data_bounds, data_crs))


def get_resolution((bounds, crs), (height, width)):
    t = transform.from_bounds(*bounds, width=width, height=height)

    return abs(t.a), abs(t.e)


def get_resolution_in_meters((bounds, crs), (height, width)):
    if crs.is_geographic:
        left = (bounds[0], (bounds[1] + bounds[3]) / 2)
        right = (bounds[2], (bounds[1] + bounds[3]) / 2)
        top = ((bounds[0] + bounds[2]) / 2, bounds[3])
        bottom = ((bounds[0] + bounds[2]) / 2, bounds[1])

        return (haversine(left, right) * 1000 / width,
                haversine(top, bottom) * 1000 / height)

    return get_resolution((bounds, crs), (height, width))


@lru_cache(maxsize=1024)
def get_source(path):
    """Cached source opening."""
    with rasterio.Env(CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.vrt,.tif,.ovr,.msk'):
        return rasterio.open(path)


def get_zoom(resolution, op=round):
    return int(op(math.log((2 * math.pi * 6378137) /
                           (resolution * 256)) / math.log(2)))


def read_window(src, (bounds, bounds_crs), (height, width)):
    if bounds_crs == WEB_MERCATOR_CRS:
        extent = (-20037508.342789244, -20037508.342789244,
                  20037508.342789244, 20037508.342789244)
    elif bounds_crs == WGS84_CRS:
        extent = (-180, -90, 180, 90)
    else:
        raise Exception("Unsupported CRS: {}".format(bounds_crs))

    if bounds_crs == WEB_MERCATOR_CRS:
        # special case for web mercator; use a target image size that most
        # closely matches the source resolution (and is a power of 2)
        zoom = get_zoom(max(get_resolution_in_meters(
            (src.bounds, src.crs), (src.height, src.width))), op=math.ceil)

        dst_width = dst_height = (2 ** zoom) * 256
        resolution = ((extent[2] - extent[0]) / dst_width,
                      (extent[3] - extent[1]) / dst_height)

        dst_transform = Affine(resolution[0], 0.0, extent[0],
                               0.0, -resolution[1], extent[3])
    else:
        # use a target image size that most closely matches the target
        # resolution
        resolution = get_resolution((bounds, bounds_crs), (height, width))
        extent_width = extent[2] - extent[0]
        extent_height = extent[3] - extent[1]
        dst_width = (1 / resolution[0]) * extent_width
        dst_height = (1 / resolution[1]) * extent_height

        # ensure that we end up with a clean multiple of the target size (until
        # rasterio uses floating point window offsets)
        if width % 2 == 1 or height % 2 == 1:
            dst_width *= 2
            dst_height *= 2
            resolution = [res / 2 for res in resolution]

        dst_transform = Affine(resolution[0], 0.0, extent[0],
                               0.0, -resolution[1], extent[3])

    with WarpedVRT(
        src,
        src_nodata=src.nodata,
        dst_crs=bounds_crs,
        dst_width=dst_width,
        dst_height=dst_height,
        dst_transform=dst_transform,
        resampling=Resampling.lanczos,
    ) as vrt:
        dst_window = vrt.window(*bounds)

        data = vrt.read(
            out_shape=(vrt.count, height, width),
            window=dst_window,
        )

        if vrt.nodata is not None:
            data = _mask(data, vrt.nodata)
        else:
            data = np.ma.masked_array(data, mask=False)

        data = data.astype(np.float32)

        return (data, (bounds, bounds_crs))


# TODO does buffer actually belong here, vs. being the responsibility of the
# calling code?
def render(
    (bounds, bounds_crs),
    shape,
    target_crs,
    format,
    transformation=None,
    buffer=0
):
    """Render data intersecting bounds into shape using an optional
    transformation."""
    resolution = get_resolution((bounds, bounds_crs), shape)
    resolution_m = get_resolution_in_meters((bounds, bounds_crs), shape)

    effective_buffer = buffer
    offset = 0

    if transformation and hasattr(transformation, 'buffer'):
        effective_buffer = buffer + transformation.buffer
        offset = transformation.buffer

    # apply buffer
    shape = [dim + (2 * effective_buffer) for dim in shape]
    bounds = [p - (effective_buffer * resolution[i % 2]) if i < 2 else
              p + (effective_buffer * resolution[i % 2])
              for i, p in enumerate(bounds)]

    sources = mosaic.get_sources((bounds, bounds_crs), resolution_m)

    (data, (data_bounds, data_crs)) = mosaic.composite(
        sources, (bounds, bounds_crs), shape, target_crs)

    data_format = "raw"

    if transformation:
        (data, data_format) = transformation((data, (data_bounds, data_crs)))

    if effective_buffer > buffer:
        (data, (data_bounds, data_crs)) = crop(
            (data, (data_bounds, data_crs)), data_format, offset)

    return format((data, (data_bounds, data_crs)), data_format)
