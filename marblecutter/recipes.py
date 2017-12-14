# coding=utf-8
from __future__ import absolute_import, division, print_function

import logging

import numpy as np

from rio_tiler import utils
from rio_toa import reflectance

from .utils import PixelCollection, Source

BAND_MAPPING = {
    "r": 0,
    "g": 1,
    "b": 2,
}
LOG = logging.getLogger(__name__)


def apply(recipes, pixels, source=None, ds=None):
    data = pixels.data

    if "landsat8" in recipes:
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

        min_val = source.meta.get("values", {}).get(source_band, {}).get(
            "min", default_min)
        max_val = source.meta.get("values", {}).get(source_band, {}).get(
            "max", default_max)

        if (min_val == default_min and max_val == default_max
                and len(data.compressed()) > 0):
            local_min, local_max = np.percentile(data.compressed(), (2, 98))
            min_val = max(min_val, local_min)
            max_val = min(max_val, local_max)

        data = np.ma.where(data > 0,
                           utils.linear_rescale(
                               data,
                               in_range=[min_val, max_val],
                               out_range=[0, 1]), 0)

    if "imagery" in recipes:
        LOG.info("Applying imagery recipe")
        # normalize to 0..1 based on the range of the source type (only
        # for int*s)
        if not np.issubdtype(ds.meta["dtype"], float):
            data /= np.iinfo(ds.meta["dtype"]).max

    # TODO source.band should be pixels.band, which requires read_window to be
    # band-aware
    return PixelCollection(data, pixels.bounds, source.band)


def preprocess(sources):
    for idx, source in enumerate(sources):
        # TODO make this configurable
        # limit the number of sources used
        if idx == 15:
            return

        if "landsat8" in source.recipes:
            for target_band, source_band in iter(source.band_info.items()):
                band = BAND_MAPPING.get(target_band)
                if band is not None:
                    yield Source(
                        source.url.replace("{band}", str(source_band)),
                        source.name, source.resolution, source.band_info,
                        source.meta, source.recipes, source.acquired_at, band,
                        source.priority)
        else:
            yield source
