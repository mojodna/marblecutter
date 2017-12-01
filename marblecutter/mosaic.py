# noqa
# coding=utf-8
from __future__ import absolute_import, division, print_function

import logging

import numpy as np

from cachetools.func import lru_cache
from rasterio import warp
from rio_tiler import utils
from rio_toa import reflectance

from .utils import Bounds, PixelCollection, Source

LOG = logging.getLogger(__name__)


@lru_cache()
def get_landsat_metadata(sceneid):
    return utils.landsat_get_mtl(sceneid)["L1_METADATA_FILE"]


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

    # TODO preprocess by recipe
    actual_sources = []
    for source in sources:
        if "landsat8" in source.recipes:
            # TODO convert band column into an array; null == all,
            # 0 = 0, [0,1,2] = separate files
            # TODO or band_mapping
            for band, source_band in enumerate((4, 3, 2)):
                s = Source(
                    source.url.replace("{band}",
                                       str(source_band)), source.name,
                    source.resolution, band, source.meta, source.recipes)
                actual_sources.append(s)
        else:
            actual_sources.append(source)

    sources = actual_sources

    # iterate over available sources, sorted by decreasing resolution
    for source in sources:
        with get_source(source.url) as src:
            sources_used.append((source.name, source.url))

            LOG.info("Compositing %s (%s) as band %s", source.url, source.name,
                     source.band)

            # read a window from the source data
            # TODO ask for a buffer here, get back an updated bounding box
            # reflecting it
            # TODO pass recipes (e.g. interpolate=bilinear)
            window_data = read_window(src, canvas_bounds, dims)

            if not window_data:
                continue

            data, _ = window_data

            # TODO extract recipe implementations

            # TODO move into hints / recipes ("remove_outliers")
            if band_count == 1 and data.mask.any():
                # mask outliers (intended for DEM boundaries)
                LOG.info("masking outliers")
                data.mask[0] = np.logical_or(data.mask[0],
                                             mask_outliers(data[0], 100.))

            if "landsat8" in (source.recipes or {}):
                LOG.info("Applying landsat 8 recipe")
                sceneid, filename = source.url.split("/")[-2:]
                band = filename.split("_B")[-1][0]
                meta = get_landsat_metadata(sceneid)

                sun_elev = meta["IMAGE_ATTRIBUTES"]["SUN_ELEVATION"]
                multi_reflect = meta["RADIOMETRIC_RESCALING"].get(
                    "REFLECTANCE_MULT_BAND_{}".format(band))
                add_reflect = meta["RADIOMETRIC_RESCALING"].get(
                    "REFLECTANCE_ADD_BAND_{}".format(band))

                data = 10000 * reflectance.reflectance(
                    data, multi_reflect, add_reflect, sun_elev, src_nodata=0)

                # calculate local min/max as fallbacks
                local_min = 0
                local_max = 65535
                if len(data.compressed()) > 0:
                    local_min, local_max = np.percentile(
                        data.compressed(), (2, 98))

                min_val = source.meta.get("min", local_min)
                max_val = source.meta.get("max", local_max)

                data = np.ma.where(data > 0,
                                   utils.linear_rescale(
                                       data,
                                       in_range=[min_val, max_val],
                                       out_range=[0, 1]), 0)

                window_data = PixelCollection(data, window_data.bounds)

            if "imagery" in (source.recipes or {}):
                LOG.info("Applying imagery recipe")
                # normalize to 0..1 based on the range of the source type (only
                # for int*s)
                if not np.issubdtype(src.meta["dtype"], float):
                    data /= np.iinfo(src.meta["dtype"]).max
                    window_data = PixelCollection(data, window_data.bounds)

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
