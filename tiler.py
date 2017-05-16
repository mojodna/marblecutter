# noqa
# coding=utf-8

from __future__ import division

from functools import partial
import importlib
import logging
import math
import json
from StringIO import StringIO
import os

from cachetools.func import lru_cache, ttl_cache
import boto3
import mercantile
import numpy as np
from PIL import Image
import rasterio
from rio_color import operations
from scipy.interpolate import RectBivariateSpline


LOG = logging.getLogger(__name__)
logging.basicConfig()
S3 = boto3.resource("s3")
S3_BUCKET = os.environ["S3_BUCKET"]
S3_PREFIX = os.environ.get("S3_PREFIX", "")

# normalize prefix
if S3_PREFIX == "/":
    S3_PREFIX = ""

if not S3_PREFIX.endswith("/"):
    S3_PREFIX += "/"

if S3_PREFIX.startswith("/"):
    S3_PREFIX = S3_PREFIX[1:]


@ttl_cache(ttl=300)
def get_metadata(id, image_id=None, scene_idx=0, **kwargs):
    """Get file / scene metadata."""
    key = "{}{}/{}/scene.json".format(S3_PREFIX, id, scene_idx)

    if image_id:
        key = "{}{}/{}/{}.json".format(S3_PREFIX, id, scene_idx, image_id)

    try:
        meta = json.loads(S3.Object(S3_BUCKET, key).get()['Body'].read())
    except Exception:
        raise InvalidTileRequest(
            'Could not load s3://{}/{}'.format(S3_BUCKET, key))

    meta['bounds'] = np.clip(
        meta['bounds'], [-180, -85.05113] * 2, [180, 85.05113] * 2).tolist()

    return meta


@lru_cache(maxsize=1024)
def get_source(path):
    """Cached source opening."""
    return rasterio.open(path)


def read_window((window, buffers, window_scale), src_url, mask_url=None, scale=1): # noqa
    # TODO create buffers when interpolating even if buffers = 0
    target_tile_width = tile_width = (256 + buffers[0] + buffers[2]) * scale
    target_tile_height = tile_height = (256 + buffers[1] + buffers[3]) * scale

    window_width = (window[1][1] - window[1][0])
    window_height = (window[0][1] - window[0][0])

    # compare window to tile width to see how much we're up/downsampling
    scale_factor = math.ceil(256 / (window_width - buffers[0] - buffers[2]))

    if scale_factor > 1:
        # respect the window size so it can be interpolated cleanly
        tile_width = int(min(window_width, target_tile_width))
        tile_height = int(min(window_height, target_tile_height))

    buffers = map(lambda x: int(x * scale), buffers)

    with rasterio.Env(CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.vrt,.tif,.ovr,.msk'):
        src = get_source(src_url)

        # TODO read the data and the mask in parallel
        if mask_url:
            data = src.read(
                out_shape=(src.count, tile_height, tile_width),
                window=window,
            )

            # handle masking ourselves (src.read(masked=True) doesn't use
            # overviews)
            mask = None
            if src.nodata is not None:
                # some datasets use the min value but report an alternate nodata value
                nodata_alt = None
                if np.issubdtype(data.dtype, int):
                    nodata_alt = np.iinfo(data.dtype).min
                else:
                    nodata_alt = np.finfo(data.dtype).min

                mask = np.where((data == src.nodata) | (data == nodata_alt), True, False)

            if src.count == 1:
                data = data.astype(np.float32)

            if src.count == 1 and scale_factor > 1:
                interpolated_tile_width = int(tile_width * scale_factor * scale)
                interpolated_tile_height = int(tile_height * scale_factor * scale)
                x = np.arange(0, interpolated_tile_width, interpolated_tile_width / tile_width)
                y = np.arange(0, interpolated_tile_height, interpolated_tile_height / tile_height)
                interp = RectBivariateSpline(x, y, data[0])

                data = interp(
                    np.arange(0, interpolated_tile_width),
                    np.arange(0, interpolated_tile_height),
                )

                if mask is not None:
                    interp_mask = RectBivariateSpline(x, y, mask[0])
                    mask = interp_mask(
                        np.arange(0, interpolated_tile_width),
                        np.arange(0, interpolated_tile_height),
                    )

                # extra buffer (for interpolation)
                offsets = map(lambda x: int(x / window_scale) - x, buffers)
                offsets[2:] = map(lambda (x, y): x - y, zip(
                    data.shape, offsets[2:]))

                data = np.ma.masked_array([data], mask=[mask])[:, offsets[1]:offsets[3], offsets[0]:offsets[2]]
            else:
                data = np.ma.masked_array(data, mask=mask)

            # apply external masks
            mask = get_source(mask_url)
            mask_data = mask.read(
                out_shape=(1, target_tile_height, target_tile_width),
                window=window,
            ).astype(np.bool)

            return (np.ma.masked_array(data, mask=~mask_data), buffers)
        else:
            # TODO eventually we're going to want to port the interpolation
            # from ^^
            data = src.read(
                out_shape=(src.count, tile_height, tile_width),
                window=window,
            )

            # handle masking ourselves (src.read(masked=True) doesn't use
            # overviews)
            data = np.ma.masked_values(data, src.nodata, copy=False)

            if src.count == 3:
                # assume RGB
                # no alpha channel, create one
                alpha = (
                    ~data.mask * np.iinfo(data.dtype).max
                ).astype(data.dtype)

                return (np.concatenate((data, alpha)), buffers)
            else:
                # assume single-band
                return (data, buffers)


def make_window(src_tile_zoom, tile, buffer=0):
    """Create a window in src_tile_zoom-aligned coordinates."""
    dz = src_tile_zoom - tile.z
    x = 2**dz * tile.x
    y = 2**dz * tile.y
    mx = 2**dz * (tile.x + 1)
    my = 2**dz * (tile.y + 1)
    dx = mx - x
    dy = my - y
    top = (2**src_tile_zoom * 256) - 1
    scale = 2**dz
    left_buffer = right_buffer = top_buffer = bottom_buffer = 0

    tile_width = 256
    tile_height = 256

    # y, x (rows, columns)
    # window is measured in pixels at src_tile_zoom
    window = [
        [
            int(math.floor(top - (top - (tile_height * y)))),
            int(math.ceil(
                top - (top - ((tile_height * y) + tile_height * dy)))),
        ],
        [
            int(math.floor(tile_width * x)),
            int(math.ceil((tile_width * x) + tile_width * dx)),
        ]
    ]

    if buffer > 0:
        if window[1][0] > 0:
            left_buffer = buffer

        if window[1][1] < top:
            right_buffer = buffer

        if window[0][0] > 0:
            top_buffer = buffer

        if window[0][1] < top:
            bottom_buffer = buffer

        window[1][0] -= left_buffer * math.ceil(scale)
        window[1][1] += right_buffer * math.ceil(scale)
        window[0][0] -= top_buffer * math.ceil(scale)
        window[0][1] += bottom_buffer * math.ceil(scale)

    return (window, (left_buffer, bottom_buffer, right_buffer, top_buffer), scale)


def read_masked_window(source, tile, scale=1, buffer=0): # noqa
    return read_window(
        make_window(source['meta']['approximateZoom'], tile, buffer=buffer),
        source['meta'].get('source'),
        source['meta'].get('mask'),
        scale=scale,
    )


def intersects(tile): # noqa
    t = mercantile.bounds(*tile)

    def _intersects(src):
        (left, bottom, right, top) = src['bounds']
        return not(
            left >= t.east or
            right <= t.west or
            top <= t.south or
            bottom >= t.north
        )

    return _intersects


def render_tile(meta, tile, scale=1, buffer=0):
    """Composite data from all sources into a single tile."""
    src_url = meta['meta'].get('source')
    if src_url:
        return read_window(
            make_window(meta['meta']['approximateZoom'], tile, buffer=buffer),
            src_url,
            meta['meta'].get('mask'),
            scale=scale
        )
    else:
        # optimize by filtering sources to only include those that apply to
        # this tile (only used without PostGIS)
        sources = filter(intersects(tile), meta['meta'].get('sources', []))

        if len(sources) == 1:
            return read_window(
                make_window(
                    sources[0]['meta']['approximateZoom'],
                    tile,
                    buffer=buffer
                ),
                sources[0]['meta']['source'],
                sources[0]['meta'].get('mask'),
                scale=scale,
            )

        data = None
        buffers = None

        for (d, b) in map(partial(
            read_masked_window,
            tile=tile,
            scale=scale,
            buffer=buffer,
        ), sources):
            if buffers is None:
                buffers = b

            if buffers != b:
                raise Exception(
                    'Buffer sizes should always match: {} != {}'.format(
                        buffers, b))

            if data is None:
                # TODO what if dtypes don't match?
                if d.shape[0] == 1:
                    data = d.astype(np.float32)
                else:
                    # pass multi-band data through
                    data = d
            else:
                data = np.ma.where(d.mask, data, d)
                data.mask = np.logical_and(data.mask, d.mask)

            if data.shape != d.shape:
                raise Exception(
                    'Data shapes should always match: {} != {}'.format(
                        data.shape, d.shape))

        if data is None:
            # TODO do something better than this when no data is available
            # how many bands should be returned?
            raise NoDataException()

        return (data, buffers)


class InvalidTileRequest(Exception): # noqa
    status_code = 404

    def __init__(self, message, status_code=None, payload=None): # noqa
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self): # noqa
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv


class NoDataException(Exception): # noqa
    pass


def get_bounds(id, **kwargs): # noqa
    return get_metadata(id, **kwargs)['bounds']


def get_renderer(renderer):
    return importlib.import_module(renderer)

def read_tile(meta, tile, renderer='hillshade', scale=1, **kwargs):
    """Fetch tile data and render as a PNG."""
    renderer = get_renderer(renderer)
    maxzoom = int(meta['maxzoom'])
    minzoom = int(meta['minzoom'])

    if not minzoom <= tile.z <= maxzoom:
        raise InvalidTileRequest(
            'Invalid zoom: {} outside [{}, {}]'.format(
                tile.z, minzoom, maxzoom))

    sw = mercantile.tile(*meta['bounds'][0:2], zoom=tile.z)
    ne = mercantile.tile(*meta['bounds'][2:4], zoom=tile.z)

    if not sw.x <= tile.x <= ne.x:
        raise InvalidTileRequest(
            'Invalid x coordinate: {} outside [{}, {}]'.format(
                tile.x, sw.x, ne.x))

    if not ne.y <= tile.y <= sw.y:
        raise InvalidTileRequest(
            'Invalid y coordinate: {} outside [{}, {}]'.format(
                tile.y, sw.y, ne.y))

    buffer = getattr(renderer, 'BUFFER', 0)
    scale = getattr(renderer, 'SCALE', scale)

    (data, buffers) = render_tile(meta, tile, scale=scale, buffer=buffer)

    if data.shape[0] == 1:
        return renderer.render(tile, (data, buffers))

    # 8-bit per pixel
    target_dtype = np.uint8

    # default values from rio color atmo
    ops = meta['meta'].get('operations')
    if ops:
        # scale to (0..1)
        floats = (data * 1.0 / np.iinfo(data.dtype).max).astype(np.float32)

        for func in operations.parse_operations(ops):
            floats = func(floats)

        # scale back to uint8
        data = (floats * np.iinfo(target_dtype).max).astype(target_dtype)

    if data.dtype != target_dtype:
        # rescale
        try:
            data = (
                data * (np.iinfo(target_dtype).max / np.iinfo(data.dtype).max)
            ).astype(target_dtype)
        except Exception:
            raise Exception(
                'Not enough information to rescale; source is "{}""'.format(
                    data.dtype))

    imgarr = np.ma.transpose(data, [1, 2, 0])

    out = StringIO()
    im = Image.fromarray(imgarr, 'RGBA')
    im.save(out, 'png')

    return ('image/png', out.getvalue())
