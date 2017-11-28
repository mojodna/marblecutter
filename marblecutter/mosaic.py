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


def composite(sources, bounds, dims, target_crs, band_count):
    """Composite data from sources into a single raster covering bounds, but in
    the target CRS."""
    # avoid circular dependencies
    from . import _nodata, get_source, read_window

    height, width = dims
    ((left, right), (bottom, top)) = warp.transform(
        bounds.crs, target_crs, bounds.bounds[::2], bounds.bounds[1::2])
    canvas = np.ma.zeros(
        (band_count, height, width),
        dtype=np.float32,
        fill_value=_nodata(np.float32))
    canvas.mask = True
    canvas_bounds = Bounds((left, bottom, right, top), target_crs)

    sources_used = list()

    # iterate over available sources, sorted by decreasing resolution
    for source in sources:
        with get_source(source.url) as src:
            sources_used.append((source.name, source.url))

            LOG.info("Compositing %s (%s)...", source.url, source.name)

            # read a window from the source data
            # TODO ask for a buffer here, get back an updated bounding box
            # reflecting it
            # TODO pass recipes (e.g. interpolate=bilinear)
            window_data = read_window(src, canvas_bounds, dims)

        if not window_data:
            continue

        data, _ = window_data
        if band_count == 1 and data.mask.any():
            # mask outliers (intended for DEM boundaries)
            LOG.info("masking outliers")
            data.mask[0] = np.logical_or(data.mask[0],
                                         mask_outliers(data[0], 100.))

        # paste (and reproject) the resulting data onto a canvas
        # TODO should band be added to PixelCollection?
        canvas = paste(window_data,
                       PixelCollection(canvas, canvas_bounds), source.band)

        # TODO get the sub-array that contains nodata pixels and only fetch
        # sources that could potentially fill those (see
        # rasterio.windows.get_data_window for the inverse)
        # See https://codereview.stackexchange.com/a/132933 for an example
        if not canvas.mask.any():
            # stop if all pixels are valid
            break

    return sources_used, PixelCollection(canvas, canvas_bounds)


def paste(window_pixels, canvas_pixels, band=None):
    """ "Reproject" src data into the correct position within a larger image"""
    window_data, (window_bounds, window_crs) = window_pixels
    canvas, (canvas_bounds, canvas_crs) = canvas_pixels
    if window_crs != canvas_crs:
        raise Exception(
            "CRSes must match: {} != {}".format(window_crs, canvas_crs))

    if window_bounds != canvas_bounds:
        raise Exception(
            "Bounds must match: {} != {}".format(window_bounds, canvas_bounds))

    if band is None and window_data.shape != canvas.shape:
        raise Exception("Data shapes must match: {} != {}".format(
            window_data.shape, canvas.shape))

    if band is None:
        merged = np.ma.where(canvas.mask & ~window_data.mask, window_data,
                             canvas)
        merged.fill_value = canvas.fill_value
    else:
        merged_band = np.ma.where(canvas.mask[band] & ~window_data.mask,
                                  window_data, canvas[band])
        canvas[band] = merged_band
        merged = canvas

    return merged
