# coding=utf-8
from __future__ import absolute_import, division, print_function

from builtins import str
import logging
import math
import unicodedata
import itertools

import numpy as np

import rasterio
from haversine import haversine
from rasterio import transform, warp, windows
from rasterio._err import CPLE_OutOfMemoryError
from rasterio.crs import CRS
from rasterio.enums import ColorInterp, MaskFlags
from rasterio.features import geometry_mask
from rasterio.transform import Affine, from_bounds
from rasterio.vrt import WarpedVRT
from rasterio.warp import Resampling, transform_geom

from . import mosaic
from .stats import Timer
from .utils import Bounds, PixelCollection

EARTH_RADIUS = 6378137
WEB_MERCATOR_CRS = CRS.from_epsg(3857)
WGS84_CRS = CRS.from_epsg(4326)
LOG = logging.getLogger(__name__)

EXTENTS = {
    str(WEB_MERCATOR_CRS): (
        -math.pi * EARTH_RADIUS,
        -math.pi * EARTH_RADIUS,
        math.pi * EARTH_RADIUS,
        math.pi * EARTH_RADIUS,
    ),
    str(WGS84_CRS): (
        math.degrees(-math.pi),
        math.degrees(-math.pi / 2),
        math.degrees(math.pi),
        math.degrees(math.pi / 2),
    ),
}


class InvalidTileRequest(Exception):

    def __init__(self, message, payload=None):
        Exception.__init__(self)
        self.message = message
        self.payload = payload

    def to_dict(self):  # noqa
        rv = dict(self.payload or ())
        rv["message"] = self.message
        return rv


class NoCatalogAvailable(Exception):
    pass


class NoDataAvailable(Exception):
    pass


def _isimage(data_format):
    return data_format.upper() in ["RGB", "RGBA"]


def _mask(data, nodata):
    if np.issubdtype(data.dtype, np.floating):
        return np.ma.masked_values(data, nodata, copy=False)

    return np.ma.masked_equal(data, nodata, copy=False)


def _nodata(dtype):
    if np.issubdtype(dtype, np.floating):
        return np.finfo(dtype).min
    else:
        return np.iinfo(dtype).min


def crop(pixel_collection, data_format, offsets):
    data, (bounds, data_crs), _, _ = pixel_collection
    left, bottom, right, top = offsets

    if _isimage(data_format):
        width, height, _ = data.shape
        t = transform.from_bounds(*bounds, width=width, height=height)

        data = data[top:height - bottom, left:width - right, :]

        cropped_window = windows.Window(left, top, width, height)
        cropped_bounds = windows.bounds(cropped_window, t)

        return PixelCollection(data, Bounds(cropped_bounds, data_crs))

    _, height, width = data.shape
    t = transform.from_bounds(*bounds, width=width, height=height)

    data = data[:, top:height - bottom, left:width - right]

    cropped_window = windows.Window(left, top, width, height)
    cropped_bounds = windows.bounds(cropped_window, t)

    return PixelCollection(data, Bounds(cropped_bounds, data_crs))


def get_extent(crs):
    return EXTENTS[str(crs)]


def get_resolution(bounds, dims):
    height, width = dims
    t = transform.from_bounds(*bounds.bounds, width=width, height=height)

    return abs(t.a), abs(t.e)


def get_resolution_in_meters(bounds, dims):
    if bounds.crs.is_geographic:
        bounds, _ = bounds
        height, width = dims

        left = (bounds[0], (bounds[1] + bounds[3]) / 2)
        right = (bounds[2], (bounds[1] + bounds[3]) / 2)
        top = ((bounds[0] + bounds[2]) / 2, bounds[3])
        bottom = ((bounds[0] + bounds[2]) / 2, bounds[1])

        return (
            haversine(left, right) * 1000 / width,
            haversine(top, bottom) * 1000 / height,
        )

    return get_resolution(bounds, dims)


def get_source(path):
    """Cached source opening."""
    with rasterio.Env():
        return rasterio.open(path)


def get_zoom(resolution, op=round):
    return max(
        0, int(op(math.log((2 * math.pi * 6378137) / (resolution * 256)) / math.log(2)))
    )


def read_window(src, bounds, target_shape, source):
    source_resolution = get_resolution_in_meters(
        Bounds(src.bounds, src.crs), (src.height, src.width)
    )
    target_resolution = get_resolution(bounds, target_shape)

    # GDAL chooses target extents such that reprojected pixels are square; this
    # may produce pixel offsets near the edges of projected bounds
    #   http://lists.osgeo.org/pipermail/gdal-dev/2016-August/045046.html
    #
    # A workaround for this is to produce a VRT with the explicit target extent
    # in projected coordinates (assuming that the target CRS is known).
    # Otherwise, we could tweak the origin (.c, .f) of the generated
    # dst_transform, but that would require knowing projected bounds of all
    # CRSes in use.

    if (
        "dem" in source.recipes
        and bounds.crs == WEB_MERCATOR_CRS
        and (
            target_resolution[0] > source_resolution[0]
            and target_resolution[1] > source_resolution[1]
        )
    ):
        # special case for web Mercator to prevent crosshatch artifacts; use a
        # target image size that most closely matches the source resolution
        # (and is a power of 2)
        zoom = min(
            22,  # going beyond this results in overflow within GDAL
            get_zoom(
                max(
                    get_resolution_in_meters(
                        Bounds(src.bounds, src.crs), (src.height, src.width)
                    )
                ),
                op=math.ceil,
            ),
        )

        dst_width = dst_height = (2 ** zoom) * 256
        extent = get_extent(bounds.crs)
        resolution = (
            (extent[2] - extent[0]) / dst_width, (extent[3] - extent[1]) / dst_height
        )

        dst_transform = Affine(
            resolution[0], 0.0, extent[0], 0.0, -resolution[1], extent[3]
        )
    else:
        resolution = None

        if (
            target_resolution[0] < source_resolution[0]
            or target_resolution[1] < source_resolution[1]
        ):
            # provide resolution for improved resampling when overzooming
            resolution = target_resolution

        (dst_transform, dst_width, dst_height) = warp.calculate_default_transform(
            src.crs,
            bounds.crs,
            src.width,
            src.height,
            *src.bounds,
            resolution=resolution
        )

    # Some OAM sources have invalid NODATA values (-1000 for a file with a
    # dtype of Byte). rasterio returns None under these circumstances
    # (indistinguishable from sources that actually have no NODATA values).
    # Providing a synthetic value "correctly" masks the output at the expense
    # of masking valid pixels with that value. This was previously (partially;
    # in the form of the bounding box but not NODATA pixels) addressed by
    # creating a VRT that mapped the mask to an alpha channel (something we
    # can't do w/o adding nDstAlphaBand to rasterio/_warp.pyx).
    #
    # Creating external masks and reading them separately (as below) is a
    # better solution, particularly as it avoids artifacts introduced when the
    # NODATA values are resampled using something other than nearest neighbor.

    if any([ColorInterp.palette in src.colorinterp]):
        resampling = Resampling[source.recipes.get("resample", "mode")]
    else:
        resampling = Resampling[source.recipes.get("resample", "bilinear")]

    src_nodata = source.recipes.get("nodata", source.meta.get("nodata", src.nodata))
    add_alpha = False

    if (
        any([MaskFlags.per_dataset in flags for flags in src.mask_flag_enums])
        and not any([MaskFlags.alpha in flags for flags in src.mask_flag_enums])
    ):
        # prefer the mask if available
        src_nodata = None
        add_alpha = True

    w, s, e, n = bounds.bounds
    vrt_transform = (
        Affine.translation(w, n)
        * Affine.scale(dst_transform.a, dst_transform.e)
        * Affine.identity()
    )
    vrt_width = math.floor((e - w) / dst_transform.a)
    vrt_height = math.floor((s - n) / dst_transform.e)

    with WarpedVRT(
        src,
        src_nodata=src_nodata,
        crs=bounds.crs,
        width=vrt_width,
        height=vrt_height,
        transform=vrt_transform,
        resampling=resampling,
        add_alpha=add_alpha,
    ) as vrt:
        dst_window = vrt.window(*bounds.bounds)

        data = vrt.read(out_shape=(vrt.count,) + target_shape, window=dst_window)

        mask = np.ma.nomask
        if source.mask:
            with rasterio.Env(OGR_ENABLE_PARTIAL_REPROJECTION=True):
                geom_mask = transform_geom(WGS84_CRS, bounds.crs, source.mask)

            mask_transform = from_bounds(
                *bounds.bounds, height=target_shape[0], width=target_shape[1]
            )
            mask = geometry_mask(
                [geom_mask], target_shape, transform=mask_transform, invert=True
            )

        if any([ColorInterp.alpha in vrt.colorinterp]):
            alpha_idx = vrt.colorinterp.index(ColorInterp.alpha)
            mask = [~data[alpha_idx] | mask] * (vrt.count - 1)
            bands = [data[i] for i in range(0, vrt.count) if i != alpha_idx]
            data = np.ma.masked_array(bands, mask=mask)
        else:
            # mask with NODATA values
            if src_nodata is not None and vrt.nodata is not None:
                data = _mask(data, vrt.nodata)
                data.mask = data.mask | mask
            else:
                data = np.ma.masked_array(data, mask=mask)

    return PixelCollection(data, bounds)


def render(
    bounds,
    shape,
    target_crs,
    format,
    expand,
    catalog=None,
    sources=None,
    transformation=None,
):
    """Render data intersecting bounds into shape using an optional
    transformation."""
    resolution_m = get_resolution_in_meters(bounds, shape)
    stats = []

    if sources is None and catalog is None:
        raise Exception("Either sources or a catalog must be provided.")

    if transformation:
        bounds, shape, offsets = transformation.expand(bounds, shape)

    if sources is None and catalog is not None:
        with Timer() as t:
            sources = catalog.get_sources(bounds, resolution_m)
        stats.append(("Get Sources", t.elapsed))

    # clone sources to prevent materializing the iterator
    sources, s = itertools.tee(sources or [])

    try:
        # attempt to fetch the next tee'd source
        next(s)
    except StopIteration:
        raise NoDataAvailable()

    with Timer() as t:
        sources_used, pixels = mosaic.composite(
            sources, bounds, shape, target_crs, expand
        )
    stats.append(("Composite", t.elapsed))

    if pixels.data is None:
        raise NoDataAvailable()

    data_format = "raw"

    if transformation:
        with Timer() as t:
            pixels, data_format = transformation.transform(pixels)
        stats.append(("Transform", t.elapsed))

        with Timer() as t:
            pixels = transformation.postprocess(pixels, data_format, offsets)

        stats.append(("Post-process", t.elapsed))

    with Timer() as t:
        (content_type, formatted) = format(pixels, data_format, sources_used)
    stats.append(("Format", t.elapsed))

    headers = {
        "Content-Type": content_type,
        "Server-Timing": [
            'op{};desc="{}";dur={:0.2f}'.format(i, name, time * 1000)
            for (i, (name, time)) in enumerate(stats)
        ]
        + [
            'src{};desc="{} - {}"'.format(
                i,
                unicodedata.normalize("NFKD", str(name)).replace('"', '\\"').encode(
                    "ascii", "ignore"
                ).decode(
                    "ascii"
                ),
                url,
            )
            for (i, (name, url)) in enumerate(sources_used)
        ],
    }

    return (headers, formatted)
