# noqa
# coding=utf-8
from __future__ import absolute_import, division, print_function

import logging

import numpy as np

from rasterio import warp

from .utils import Bounds, PixelCollection

LOG = logging.getLogger(__name__)


def mask_outliers(data, m=2.):
    d = np.abs(data - np.median(data.compressed()))
    mdev = np.median(d.compressed())
    s = d / mdev if mdev else 0.
    return np.where(s < m, False, True)


def composite(sources, bounds, dims, target_crs):
    """Composite data from sources into a single raster covering bounds, but in
    the target CRS."""
    from . import _nodata, get_source, read_window

    height, width = dims
    ((left, right), (bottom, top)) = warp.transform(
        bounds.crs, target_crs, bounds.bounds[::2], bounds.bounds[1::2])
    canvas = None
    canvas_bounds = Bounds((left, bottom, right, top), target_crs)

    sources_used = list()

    # iterate over available sources, sorted by decreasing resolution
    for (url, source_name, resolution) in sources:
        with get_source(url) as src:
            if canvas is None:
                # infer the number of bands to use from the first available
                # source
                canvas = np.ma.zeros(
                    (src.count, height, width),
                    dtype=np.float32,
                    fill_value=_nodata(np.float32))
                canvas.mask = True
                canvas.fill_value = _nodata(np.float32)

            sources_used.append((source_name, url))

            LOG.info("Compositing %s (%s)...", url, source_name)

            # read a window from the source data
            # TODO ask for a buffer here, get back an updated bounding box
            # reflecting it
            # TODO NamedTuple for bounds (bounds + CRS)
            window_data = read_window(src, canvas_bounds, dims)

        if not window_data:
            continue

        data, _ = window_data
        if data.shape[0] == 1 and data.mask.any():
            # mask outliers (intended for DEM boundaries)
            LOG.info("masking outliers")
            data.mask[0] = np.logical_or(data.mask[0],
                                         mask_outliers(data[0], 100.))

        # paste (and reproject) the resulting data onto a canvas
        # TODO NamedTuple for data (data + bounds)
        canvas = paste(window_data, PixelCollection(canvas, canvas_bounds))

        # TODO get the sub-array that contains nodata pixels and only fetch
        # sources that could potentially fill those (see
        # windows.get_data_window for the inverse)
        # See https://codereview.stackexchange.com/a/132933 for an example
        if not canvas.mask.any():
            # stop if all pixels are valid
            break

    return sources_used, PixelCollection(canvas, canvas_bounds)


def paste(window_pixels, canvas_pixels):
    """ "Reproject" src data into the correct position within a larger image"""
    window_data, (window_bounds, window_crs) = window_pixels
    canvas, (canvas_bounds, canvas_crs) = canvas_pixels
    if window_crs != canvas_crs:
        raise Exception(
            "CRSes must match: {} != {}".format(window_crs, canvas_crs))

    if window_bounds != canvas_bounds:
        raise Exception(
            "Bounds must match: {} != {}".format(window_bounds, canvas_bounds))

    if window_data.shape != canvas.shape:
        raise Exception("Data shapes must match: {} != {}".format(
            window_data.shape, canvas.shape))

    merged = np.ma.where(canvas.mask & ~window_data.mask, window_data, canvas)
    merged.fill_value = canvas.fill_value

    return merged
