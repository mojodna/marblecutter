# noqa
# coding=utf-8
from __future__ import absolute_import, division, print_function

import logging
import multiprocessing
from concurrent import futures

import numpy as np

from rasterio import warp

from . import recipes
from .utils import Bounds, PixelCollection

LOG = logging.getLogger(__name__)


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

    sources = recipes.preprocess(sources)

    def _read_window(source):
        with get_source(source.url) as src:
            LOG.info("Compositing %s (%s) as band %s", source.url, source.name,
                     source.band)

            # read a window from the source data
            # TODO ask for a buffer here, get back an updated bounding box
            # reflecting it
            # TODO pass recipes (e.g. interpolate=bilinear)
            window_data = read_window(src, canvas_bounds, dims, source.recipes)

            if not window_data:
                return

            window_data = recipes.apply(
                source.recipes, window_data, source=source, ds=src)

            return source, window_data

    # iterate over available sources, sorted by decreasing "quality"
    with futures.ThreadPoolExecutor(
            max_workers=multiprocessing.cpu_count() * 5) as executor:
        ws = executor.map(_read_window, sources)

    sources_used = []

    for source, window_data in ws:
        # paste the resulting data onto a canvas

        if window_data.data is None:
            continue

        canvas = paste(window_data, PixelCollection(canvas, canvas_bounds))
        sources_used.append(source)

        if not canvas.mask.any():
            # stop if all pixels are valid
            break

    return map(lambda s: (s.name, s.url), sources_used), PixelCollection(
        canvas, canvas_bounds)


def paste(window_pixels, canvas_pixels):
    """ "Reproject" src data into the correct position within a larger image"""
    window_data, (window_bounds, window_crs), band = window_pixels
    canvas, (canvas_bounds, canvas_crs), _ = canvas_pixels
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
