# noqa
# coding=utf-8
from __future__ import absolute_import, division, print_function

import logging
import multiprocessing
from concurrent import futures

import numpy as np

from rasterio import warp
from rio_tiler import utils
from rio_toa import reflectance

from .utils import Bounds, PixelCollection, Source

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

    # TODO preprocess by recipe
    actual_sources = []
    band_mapping = {
        "r": 0,
        "g": 1,
        "b": 2,
    }
    for source in sources:
        if "landsat8" in source.recipes:
            for target_band, source_band in source.band_info.iteritems():
                band = band_mapping.get(target_band)
                if band is not None:
                    s = Source(
                        source.url.replace("{band}", str(source_band)),
                        source.name, source.resolution, source.band_info,
                        source.meta, source.recipes, band)
                    actual_sources.append(s)
        else:
            actual_sources.append(source)

    sources = actual_sources

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

            data = window_data.data

            # TODO extract recipe implementations

            if "mask_outliers" in source.recipes:
                # mask outliers (intended for DEM boundaries)
                LOG.info("masking outliers")
                data.mask[0] = np.logical_or(data.mask[0],
                                             mask_outliers(data[0], 100.))

            if "landsat8" in source.recipes:
                LOG.info("Applying landsat 8 recipe")
                source_band = source.url.split("/")[-1].split("_B")[1][0]

                sun_elev = source.meta["L1_METADATA_FILE"]["IMAGE_ATTRIBUTES"][
                    "SUN_ELEVATION"]
                multi_reflect = source.meta[
                    "L1_METADATA_FILE"]["RADIOMETRIC_RESCALING"].get(
                        "REFLECTANCE_MULT_BAND_{}".format(source_band))
                add_reflect = source.meta[
                    "L1_METADATA_FILE"]["RADIOMETRIC_RESCALING"].get(
                        "REFLECTANCE_ADD_BAND_{}".format(source_band))

                data = 10000 * reflectance.reflectance(
                    data, multi_reflect, add_reflect, sun_elev, src_nodata=0)

                # calculate local min/max as fallbacks
                default_min = 0
                default_max = 65535

                min_val = source.meta.get("values",
                                          {}).get(source_band, {}).get(
                                              "min", default_min)
                max_val = source.meta.get("values",
                                          {}).get(source_band, {}).get(
                                              "max", default_max)

                if (min_val == default_min and max_val == default_max
                        and len(data.compressed()) > 0):
                    local_min, local_max = np.percentile(
                        data.compressed(), (2, 98))
                    min_val = max(min_val, local_min)
                    max_val = min(max_val, local_max)

                data = np.ma.where(data > 0,
                                   utils.linear_rescale(
                                       data,
                                       in_range=[min_val, max_val],
                                       out_range=[0, 1]), 0)

                window_data = PixelCollection(data, window_data.bounds,
                                              source.band)

            if "imagery" in source.recipes:
                LOG.info("Applying imagery recipe")
                # normalize to 0..1 based on the range of the source type (only
                # for int*s)
                if not np.issubdtype(src.meta["dtype"], float):
                    data /= np.iinfo(src.meta["dtype"]).max
                    window_data = PixelCollection(data, window_data.bounds)

            return source, window_data

    # iterate over available sources, sorted by decreasing "quality"
    with futures.ThreadPoolExecutor(
            max_workers=multiprocessing.cpu_count() * 5) as executor:
        ws = executor.map(_read_window, sources)

    sources_used = []

    for source, window_data in ws:
        # paste (and reproject) the resulting data onto a canvas

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
