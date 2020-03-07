# coding=utf-8
from __future__ import absolute_import, division, print_function

import itertools
import logging
from builtins import range
from functools import reduce

import numpy as np
import numexpr as ne
import re

from rio_pansharpen.methods import Brovey
from rio_tiler import utils
from rio_toa import reflectance

from .utils import PixelCollection, Source, make_colormap

BAND_MAPPING = {"r": 0, "g": 1, "b": 2, "pan": 4}
LOG = logging.getLogger(__name__)


def apply(recipes, pixels, expand, source=None):
    data = pixels.data
    colormap = pixels.colormap
    if np.issubdtype(data.dtype, np.floating):
        dtype_min = np.finfo(data.dtype).min
        dtype_max = np.finfo(data.dtype).max
    else:
        dtype_min = np.iinfo(data.dtype).min
        dtype_max = np.iinfo(data.dtype).max

    if data.shape[0] == 1:
        if expand and colormap:
            # create a lookup table from the source's color map
            lut = make_colormap(colormap)

            # stash the mask
            mask = data.mask

            # apply the color map
            data = lut[data[0], :]

            # re-shape to match band-style
            data = np.ma.transpose(data, [2, 0, 1])

            # re-apply the mask, merging it with pixels that were masked by the color map
            data.mask = data.mask | mask

            colormap = None

    if "landsat8" in recipes:
        LOG.info("Applying landsat 8 recipe")

        out = np.ma.empty(shape=(data.shape), dtype=np.float32)

        for bdx, source_band in enumerate((4, 3, 2)):
            sun_elev = source.meta["L1_METADATA_FILE"]["IMAGE_ATTRIBUTES"][
                "SUN_ELEVATION"
            ]
            multi_reflect = source.meta["L1_METADATA_FILE"][
                "RADIOMETRIC_RESCALING"
            ].get(
                "REFLECTANCE_MULT_BAND_{}".format(source_band)
            )
            add_reflect = source.meta["L1_METADATA_FILE"]["RADIOMETRIC_RESCALING"].get(
                "REFLECTANCE_ADD_BAND_{}".format(source_band)
            )

            min_val = source.meta.get("values", {}).get(str(source_band), {}).get(
                "min", dtype_min
            )
            max_val = source.meta.get("values", {}).get(str(source_band), {}).get(
                "max", dtype_max
            )

            band_data = 10000 * reflectance.reflectance(
                data[bdx], multi_reflect, add_reflect, sun_elev, src_nodata=0
            )

            # calculate local min/max as fallbacks
            if (
                min_val == dtype_min
                and max_val == dtype_max
                and len(data.compressed()) > 0
            ):
                local_min, local_max = np.percentile(band_data.compressed(), (2, 98))
                min_val = max(min_val, local_min)
                max_val = min(max_val, local_max)

            out[bdx] = utils.linear_rescale(
                band_data, in_range=(min_val, max_val), out_range=(0.0, 1.0)
            )

        data = out

    if "imagery" in recipes:
        LOG.info("Applying imagery recipe")


        if "rgb_bands" in recipes:
            data = np.ma.array(
                [data[i - 1] for i in recipes["rgb_bands"] if data.shape[0] >= i]
            )
        elif "expr" in recipes:
            num_bands = data.shape[0]
            expressions = recipes["expr"].split(",")
            band_names = ["b" + str(i) for i in range(1, num_bands + 1)]
            local_dict = dict(zip(band_names, data.data))

            old_mask = data.mask
            old_mask_shape = old_mask.shape
            new_mask_shape = (len(expressions), old_mask_shape[1], old_mask_shape[2])
            new_mask = np.ndarray(new_mask_shape, dtype=np.bool)
            for (expression_index, expression) in enumerate(expressions):
                # identify bands used in expression
                band_indexes = [int(i) - 1 for i in re.findall(r"(?<=b)(\d{1,2})", expression)]
                old_band_masks = [old_mask[i] for i in band_indexes]
                new_mask[expression_index] = np.logical_and.reduce(old_band_masks)
            data = np.ma.array([
                np.nan_to_num(ne.evaluate(expression.strip(), local_dict=local_dict))
                for expression in expressions
            ], mask=new_mask)
        elif data.shape[0] > 3:
            # alpha(?) band (and beyond) present; drop it (them)
            # TODO use band 4 as an alpha channel if colorinterp == alpha instead
            # TODO re-order channels if BGR (whatever colorinterp says)
            data = data[0:3]

        if "linear_stretch" in recipes:
            if recipes["linear_stretch"] == "global":
                data = utils.linear_rescale(
                    data, in_range=(np.min(data), np.max(data)), out_range=(0.0, 1.0)
                )
            elif recipes["linear_stretch"] == "per_band":
                out = np.ma.empty(shape=(data.shape), dtype=np.float32)

                for band in range(0, data.shape[0]):
                    min_val = source.meta.get("values", {}).get(band, {}).get(
                        "min", np.min(data[band])
                    )
                    max_val = source.meta.get("values", {}).get(band, {}).get(
                        "max", np.max(data[band])
                    )

                    out[band] = utils.linear_rescale(
                        data[band], in_range=(min_val, max_val), out_range=(0.0, 1.0)
                    )

                data = out
        else:
            # rescale after reducing and before increasing dimensionality
            if data.dtype != np.uint8:
                # rescale non-8-bit sources (assuming that they're raw sensor
                # data) and normalize to 0..1
                out = np.ma.empty(shape=(data.shape), dtype=np.float32)

                for band in range(0, data.shape[0]):
                    min_val = source.meta.get("values", {}).get(band, {}).get(
                        "min", dtype_min
                    )
                    max_val = source.meta.get("values", {}).get(band, {}).get(
                        "max", dtype_max
                    )

                    if (
                        min_val == dtype_min
                        and max_val == dtype_max
                        and len(data.compressed()) > 0
                    ):
                        local_min, local_max = np.percentile(
                            data[band].compressed(), (2, 98)
                        )
                        min_val = max(min_val, local_min)
                        max_val = min(max_val, local_max)

                    out[band] = utils.linear_rescale(
                        data[band], in_range=(min_val, max_val), out_range=(0.0, 1.0)
                    )

                data = out

        if not np.issubdtype(data.dtype, np.floating):
            # normalize to 0..1 based on the range of the source type (only
            # for int*s)
            data = data.astype(np.float32) / dtype_max

        if data.shape[0] == 1:
            # likely greyscale image; use the same band on all channels
            data = np.ma.array([data[0], data[0], data[0]])

    return PixelCollection(data, pixels.bounds, None, colormap)


def preprocess(sources, resolution=None):
    for idx, source in enumerate(sources):
        # TODO make this configurable
        # limit the number of sources used
        if idx == 15:
            return

        if "landsat8" in source.recipes:
            for target_band, source_band in iter(source.band_info.items()):
                band = BAND_MAPPING.get(target_band)
                s = Source(
                    source.url.replace("{band}", str(source_band)),
                    source.name,
                    source.resolution,
                    source.band_info,
                    source.meta,
                    source.recipes,
                    source.acquired_at,
                    band,
                    source.priority,
                )
                if target_band == "pan":
                    if min(resolution) < source.resolution * 2:
                        yield s
                elif band is not None:
                    yield s
        else:
            yield source


def is_rgb(band):
    return band <= 2


def _reduce_landsat_windows(canvas, window):
    from .mosaic import paste

    _, pixels = window

    return paste(pixels, canvas)


def postprocess(windows):
    from . import _nodata

    windows = list(filter(None, windows))

    landsat_windows = filter(lambda sw: "LC08_" in sw[0].url, windows)
    landsat_windows = dict(
        [
            (k, list(v))
            for k, v in itertools.groupby(
                landsat_windows, lambda x: x[0].url.split("/")[-2]
            )
        ]
    )

    pan_bands = dict(
        list(
            map(
                lambda sw: (sw[0].url.split("/")[-2], sw[1]),
                filter(lambda sw: sw[0].band == 4, filter(None, windows)),
            )
        )
    )

    for source, pixels in windows:
        if pixels is None or pixels.data is None:
            continue

        if "landsat8" in source.recipes:
            scene_id = source.url.split("/")[-2]
            source = Source(
                "/".join(source.url.split("/")[0:-1]),
                source.name,
                source.resolution,
                source.band_info,
                source.meta,
                source.recipes,
                source.acquired_at,
                None,
                source.priority,
                source.coverage,
            )

            # pick out all bands for the same scene the first time it's seen
            if scene_id in landsat_windows:
                ws = filter(
                    lambda sw: is_rgb(sw[0].band), landsat_windows.pop(scene_id)
                )
                canvas_data = np.ma.zeros(
                    (3,) + pixels.data.shape[1:],
                    dtype=pixels.data.dtype,
                    fill_value=_nodata(pixels.data.dtype),
                )
                canvas_data.mask = True

                canvas = PixelCollection(canvas_data, pixels.bounds)
                pixels = reduce(_reduce_landsat_windows, ws, canvas)

                if scene_id in pan_bands:
                    pan = pan_bands[scene_id]

                    pansharpened, _ = Brovey(
                        pixels.data, pan.data[0], 0.2, pan.data.dtype
                    )

                    yield source, PixelCollection(pansharpened, pixels.bounds)
                else:
                    yield source, pixels
        else:
            yield source, pixels
