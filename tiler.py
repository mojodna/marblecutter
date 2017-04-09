# coding=utf-8
from __future__ import division

from functools import partial
import logging
from multiprocessing.dummy import Pool
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

from hillshade import hillshade
from normal import normal


LOG = logging.getLogger(__name__)
logging.basicConfig()
S3 = boto3.resource("s3")
S3_BUCKET = os.environ["S3_BUCKET"]
S3_PREFIX = os.environ.get("S3_PREFIX", "")
pool = Pool(100)

# normalize prefix
if S3_PREFIX == "/":
    S3_PREFIX = ""

if not S3_PREFIX.endswith("/"):
    S3_PREFIX += "/"

if S3_PREFIX.startswith("/"):
    S3_PREFIX = S3_PREFIX[1:]


def get_id(id, image_id=None, scene_idx=0):
    if image_id:
        return '{}/{}/{}'.format(id, scene_idx, image_id)

    return id


@ttl_cache(ttl=300)
def get_metadata(id, image_id=None, scene_idx=0, **kwargs):
    key = "{}{}/{}/scene.json".format(S3_PREFIX, id, scene_idx)

    if image_id:
        key = "{}{}/{}/{}.json".format(S3_PREFIX, id, scene_idx, image_id)

    try:
        meta = json.loads(S3.Object(S3_BUCKET, key).get()['Body'].read())
    except:
        raise InvalidTileRequest('Could not load s3://{}/{}'.format(S3_BUCKET, key))

    meta['bounds'] = np.clip(meta['bounds'], [-180, -85.05113] * 2, [180, 85.05113] * 2).tolist()

    return meta


@lru_cache(maxsize=1024)
def get_source(path):
    return rasterio.open(path)


def read_window((window, buffers), src_url, mask_url=None, scale=1): # noqa
    tile_width = (256 + buffers[0] + buffers[2]) * scale
    tile_height = (256 + buffers[1] + buffers[3]) * scale
    scaled_buffers = map(lambda x: x * scale, buffers)
    LOG.warn('window: {}'.format(window))
    LOG.warn('scaled_buffers: {}'.format(scaled_buffers))
    # TODO we need to do something about scaled buffers here; if scale factor is 8.0, renderer.buffer needs to be 32 (not 2)

    with rasterio.Env(CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.vrt,.tif,.ovr,.msk'):
        src = get_source(src_url)

        # compare window to tile_width
        scale_factor = tile_width / (window[0][1] - window[0][0])
        LOG.warn('scale_factor: {}'.format(scale_factor))

        if 0.25 > scale_factor > 32:
            # skip this layer
            return (np.ma.masked_all((src.count, tile_width, tile_height)), scaled_buffers)

        if scale_factor > 1:
            _tile_width = tile_width
            _tile_height = tile_height
            tile_width = int(tile_width / scale_factor)
            tile_height = int(tile_height / scale_factor)

        # TODO read the data and the mask in parallel
        if mask_url:
            data = src.read(
                out_shape=(src.count, tile_width, tile_height),
                window=window
            )
            # handle masking ourselves (src.read(masked=True) doesn't use
            # overviews)
            # TODO don't create a masked array; just create a mask
            # data = np.ma.masked_values(data, src.nodata, copy=False)
            mask = None
            if src.nodata is not None:
                mask = np.where(data == src.nodata, True, False)

            if scale_factor > 1:
                tile_width = _tile_width
                tile_height = _tile_height

                LOG.warn('data[0].shape: {}'.format(data[0].shape))
                LOG.warn('tile_width: {}'.format(tile_width))

                x = np.arange(0, tile_width, scale_factor)
                LOG.warn('x.shape: {}'.format(x.shape))
                y = np.arange(0, tile_height, scale_factor)
                interp = RectBivariateSpline(x, y, data[0])

                data = interp(
                    np.arange(0, tile_width),
                    np.arange(0, tile_height),
                )

                if mask is not None:
                    LOG.warn('mask[0].shape: {}'.format(mask[0].shape))
                    interp_mask = RectBivariateSpline(x, y, mask[0])
                    mask = interp_mask(
                        np.arange(0, tile_width),
                        np.arange(0, tile_height),
                    )

                    data = np.ma.masked_array([data], mask=[mask])
            else:
                data = np.ma.masked_array(data, mask=mask)

            # apply external masks
            mask = get_source(mask_url)
            mask_data = mask.read(
                out_shape=(1, tile_width, tile_height),
                window=window
            ).astype(np.bool)

            data = np.ma.array(data, mask=~mask_data)

            return (data, scaled_buffers)
        else:
            # TODO eventually we're going to want to port the interpolation from ^^
            data = src.read(
                out_shape=(src.count, tile_width, tile_height),
                window=window
            )

            # handle masking ourselves (src.read(masked=True) doesn't use overviews)
            data = np.ma.masked_values(data, src.nodata, copy=False)

            if src.count == 3:
                # assume RGB
                # no alpha channel, create one
                alpha = (~data.mask * np.iinfo(data.dtype).max).astype(data.dtype)

                return (np.concatenate((data, alpha)), scaled_buffers)
            else:
                # assume single-band
                return (data, scaled_buffers)


def make_window(src_tile_zoom, tile, buffer=0):
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
    LOG.warn('scale (make_window): {}'.format(scale))
    LOG.warn('effective buffer: {}'.format(buffer * scale))

    # y, x (rows, columns)
    # window is measured in pixels at src_tile_zoom
    window = [[top - (top - (256 * y)), top - (top - ((256 * y) + int(256 * dy)))],
            [256 * x, (256 * x) + int(256 * dx)]]

    if buffer > 0:
        if window[1][0] > 0:
            left_buffer = buffer

        if window[1][1] < top:
            right_buffer = buffer

        if window[0][0] > 0:
            top_buffer = buffer

        if window[0][1] < top:
            bottom_buffer = buffer

        window[0][0] -= top_buffer * scale
        window[0][1] += bottom_buffer * scale
        window[1][0] -= left_buffer * scale
        window[1][1] += right_buffer * scale

    return (window, (left_buffer, bottom_buffer, right_buffer, top_buffer))


def read_masked_window(source, tile, scale=1, buffer=0):
    return read_window(
        make_window(source['meta']['approximateZoom'], tile, buffer=buffer),
        source['meta'].get('source'),
        source['meta'].get('mask'),
        scale=scale,
    )


def intersects(tile):
    t = mercantile.bounds(*tile)

    def _intersects(src):
        (left, bottom, right, top) = src['bounds']
        return not(left >= t.east or right <= t.west or top <= t.south or bottom >= t.north)

    return _intersects


def render_tile(meta, tile, scale=1, buffer=0):
    src_url = meta['meta'].get('source')
    if src_url:
        return read_window(
            make_window(meta['meta']['approximateZoom'], tile, buffer=buffer),
            src_url,
            meta['meta'].get('mask'),
            scale=scale
        )
    else:
        # optimize by filtering sources to only include those that apply to this tile
        sources = filter(intersects(tile), meta['meta'].get('sources', []))

        if len(sources) == 1:
            return read_window(
                make_window(sources[0]['meta']['approximateZoom'], tile, buffer=buffer),
                sources[0]['meta']['source'],
                sources[0]['meta'].get('mask'),
                scale=scale
            )

        data = None
        buffers = None

        # read windows in parallel and reduce
        for (d, b) in pool.map(partial(
            read_masked_window,
            tile=tile,
            scale=scale,
            buffer=buffer,
        ), sources):
            if buffers is None:
                buffers = b

            if data is None:
                # TODO what if dtypes don't match?
                if d.shape[0] == 1:
                    data = d.astype(np.float32)
                else:
                    data = d
            else:
                data = np.ma.where(~d.mask, d, data)
                data.mask = np.logical_and(data.mask, d.mask)

            # TODO check resolution of d and see how it compares to the shape
            # if it's not 1:1, convolve2d

        if data is None:
            # TODO do something better than this when no data is available
            # how many bands should be returned?
            raise Exception('No data available')

        return (data, buffers)


class InvalidTileRequest(Exception):
    status_code = 404

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv


def get_bounds(id, **kwargs):
    return get_metadata(id, **kwargs)['bounds']


def read_tile(meta, tile, renderer='hillshade', scale=1, **kwargs):
    renderer = globals()[renderer]
    maxzoom = int(meta['maxzoom'])
    minzoom = int(meta['minzoom'])

    if not minzoom <= tile.z <= maxzoom:
        raise InvalidTileRequest('Invalid zoom: {} outside [{}, {}]'.format(tile.z, minzoom, maxzoom))

    sw = mercantile.tile(*meta['bounds'][0:2], zoom=tile.z)
    ne = mercantile.tile(*meta['bounds'][2:4], zoom=tile.z)

    if not sw.x <= tile.x <= ne.x:
        raise InvalidTileRequest('Invalid x coordinate: {} outside [{}, {}]'.format(tile.x, sw.x, ne.x))

    if not ne.y <= tile.y <= sw.y:
        raise InvalidTileRequest('Invalid y coordinate: {} outside [{}, {}]'.format(tile.y, sw.y, ne.y))

    buffer = getattr(renderer, 'buffer', 0)

    (data, buffers) = render_tile(meta, tile, scale=scale, buffer=buffer)

    if data.shape[0] == 1:
        return renderer(tile, (data, buffers))

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
            data = (data * (np.iinfo(target_dtype).max / np.iinfo(data.dtype).max)).astype(target_dtype)
        except:
            raise Exception('Not enough information to rescale; source is "{}""'.format(data.dtype))

    imgarr = np.ma.transpose(data, [1, 2, 0])

    out = StringIO()
    im = Image.fromarray(imgarr, 'RGBA')
    im.save(out, 'png')

    return out.getvalue()
