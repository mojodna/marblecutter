# coding=utf-8
from __future__ import division

from functools import partial
import logging
from multiprocessing.dummy import Pool
import json
from StringIO import StringIO
import os

import matplotlib
matplotlib.use("Agg")

from matplotlib.colors import LinearSegmentedColormap
import matplotlib.pyplot as plt

from cachetools.func import lru_cache, ttl_cache
import boto3
import mercantile
import numpy as np
from PIL import Image
import rasterio
import requests
from rio_color import operations


LOG = logging.getLogger(__name__)
logging.basicConfig()
S3 = boto3.resource("s3")
S3_BUCKET = os.environ["S3_BUCKET"]
S3_PREFIX = os.environ.get("S3_PREFIX", "")
pool = Pool(100)

# from http://www.shadedrelief.com/web_relief/
EXAGGERATION = {
    0: 45.0,
    1: 29.0,
    2: 20.0,
    3: 14.0,
    4: 9.5,
    5: 6.5,
    6: 5.0,
    7: 3.6,
    8: 2.7,
    9: 2.1,
    10: 1.7,
    11: 1.4,
    12: 1.3,
    13: 1.2,
    14: 1.1,
}

GREY_HILLS_RAMP = {
    "red": [(0.0, 0.0, 0.0),
            (0.25, 0.0, 0.0),
            (180 / 255.0, 0.5, 0.5),
            (1.0, 170 / 255.0, 170 / 255.0)],
    "green": [(0.0, 0.0, 0.0),
              (0.25, 0.0, 0.0),
              (180 / 255.0, 0.5, 0.5),
              (1.0, 170 / 255.0, 170 / 255.0)],
    "blue": [(0.0, 0.0, 0.0),
             (0.25, 0.0, 0.0),
             (180 / 255.0, 0.5, 0.5),
             (1.0, 170 / 255.0, 170 / 255.0)],
}

GREY_HILLS = LinearSegmentedColormap("grey_hills", GREY_HILLS_RAMP)

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


def get_resolution(path, scale=1):
    src = get_source(path)

    # TODO affine is deprecated
    return (src.affine.a * scale, src.affine.e * scale)


def read_window((window, buffers), src_url, mask_url=None, scale=1):
    tile_width = (256 + buffers[0] + buffers[2]) * scale
    tile_height = (256 + buffers[1] + buffers[3]) * scale
    scaled_buffers = map(lambda x: x * scale, buffers)

    with rasterio.Env(CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.vrt,.tif,.ovr,.msk'):
        src = get_source(src_url)

        # TODO read the data and the mask in parallel
        if mask_url:
            data = src.read(out_shape=(3, tile_width, tile_height), window=window)
            mask = get_source(mask_url)
            mask_data = mask.read(out_shape=(1, tile_width, tile_height), window=window)

            return (np.concatenate((data, mask_data)), scaled_buffers)
        else:
            # TODO read_masked
            data = src.read(out_shape=(src.count, tile_width, tile_height), window=window)
            if src.count == 4:
                # alpha channel present
                return (data, scaled_buffers)
            elif src.count == 3:
                # assume RGB
                # no alpha channel, create one
                # TODO use src.bounds as an implicit mask
                alpha = np.full((1, tile_width, tile_height), np.iinfo(data.dtype).max, data.dtype)

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


def read_masked_window(source, tile, scale=1):
    return read_window(
        make_window(source['meta']['approximateZoom'], tile),
        source['meta'].get('source'),
        source['meta'].get('mask'),
        scale=scale
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

        data = np.zeros(shape=(4, 256 * scale, 256 * scale)).astype(np.uint8)
        buffers = (buffer, buffer, buffer, buffer)

        # read windows in parallel and alpha composite
        for (d, b) in pool.map(partial(read_masked_window, tile=tile, scale=scale), sources):
            mask = d[3] > 0
            mask = mask[np.newaxis,:]
            data = np.where(mask, d, data)
            buffers = b

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


def hillshade(tile, (data, buffers), dx, dy):
    hs = render_hillshade(tile, data[0], buffers, dx, dy)

    out = StringIO()
    plt.imsave(
        out,
        hs,
        cmap=GREY_HILLS,
        vmin=0,
        vmax=255,
        format='png',
    )

    return out.getvalue()

hillshade.buffer = 2


def normal(tile, (data, buffers), dx, dy):
    imgarr = render_normal(tile, data[0], buffers, dx, dy)

    out = StringIO()
    im = Image.fromarray(imgarr, 'RGBA')
    im.save(out, 'png')

    return out.getvalue()

normal.buffer = 2


# TODO include buffer size as a property of the renderer argument
def read_tile(id, tile, renderer=normal, scale=1, **kwargs):
    meta = get_metadata(id, **kwargs)
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

    buffer = 0
    if hasattr(renderer, 'buffer'):
        buffer = renderer.buffer

    (data, buffers) = render_tile(meta, tile, scale=scale, buffer=buffer)

    if data.shape[0] == 1:
        (dx, dy) = get_resolution(meta['meta'].get('source'), scale=scale)
        # TODO figure out what the appropriate arguments are for all output types
        return renderer(tile, (data, buffers), dx=dx, dy=dy)

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


def render_hillshade(tile, data, buffers, dx, dy):
    # TODO not buffered

    # interpolate latitudes
    bounds = mercantile.bounds(tile.x, tile.y, tile.z)
    height = data.shape[0]
    latitudes = np.interp(np.arange(height), [0, height - 1], [bounds.north, bounds.south])

    factors = 1 / np.cos(np.radians(latitudes))

    # convert to 2d array, rotate 270º, scale data
    data = data * np.rot90(np.atleast_2d(factors), 3)

    hs = hillshade(data,
        dx=dx,
        dy=dy,
        vert_exag=EXAGGERATION.get(tile.z, 1.0),
        # azdeg=315, # which direction is the light source coming from (north-south)
        # altdeg=45, # what angle is the light source coming from (overhead-horizon)
    )

    # scale hillshade values (0.0-1.0) to integers (0-255)
    hs = (255.0 * hs).astype(np.uint8)

    return hs


def hillshade(elevation, azdeg=315, altdeg=45, vert_exag=1, dx=1, dy=1, fraction=1.):
    """
    This is a slightly modified version of
    matplotlib.colors.LightSource.hillshade, modified to remove the contrast
    stretching (because that uses local min/max values).
    Calculates the illumination intensity for a surface using the defined
    azimuth and elevation for the light source.
    Imagine an artificial sun placed at infinity in some azimuth and
    elevation position illuminating our surface. The parts of the surface
    that slope toward the sun should brighten while those sides facing away
    should become darker.
    Parameters
    ----------
    elevation : array-like
        A 2d array (or equivalent) of the height values used to generate an
        illumination map
    azdeg : number, optional
        The azimuth (0-360, degrees clockwise from North) of the light
        source. Defaults to 315 degrees (from the northwest).
    altdeg : number, optional
        The altitude (0-90, degrees up from horizontal) of the light
        source.  Defaults to 45 degrees from horizontal.
    vert_exag : number, optional
        The amount to exaggerate the elevation values by when calculating
        illumination. This can be used either to correct for differences in
        units between the x-y coordinate system and the elevation
        coordinate system (e.g. decimal degrees vs meters) or to exaggerate
        or de-emphasize topographic effects.
    dx : number, optional
        The x-spacing (columns) of the input *elevation* grid.
    dy : number, optional
        The y-spacing (rows) of the input *elevation* grid.
    fraction : number, optional
        Increases or decreases the contrast of the hillshade.  Values
        greater than one will cause intermediate values to move closer to
        full illumination or shadow (and clipping any values that move
        beyond 0 or 1). Note that this is not visually or mathematically
        the same as vertical exaggeration.
    Returns
    -------
    intensity : ndarray
        A 2d array of illumination values between 0-1, where 0 is
        completely in shadow and 1 is completely illuminated.
    """
    # Azimuth is in degrees clockwise from North. Convert to radians
    # counterclockwise from East (mathematical notation).
    az = np.radians(90 - azdeg)
    alt = np.radians(altdeg)

    # Calculate the intensity from the illumination angle
    dy, dx = np.gradient(vert_exag * elevation, dy, dx)
    # The aspect is defined by the _downhill_ direction, thus the negative
    aspect = np.arctan2(-dy, -dx)
    slope = 0.5 * np.pi - np.arctan(np.hypot(dx, dy))
    intensity = (np.sin(alt) * np.sin(slope) +
                 np.cos(alt) * np.cos(slope) * np.cos(az - aspect))

    # Apply contrast stretch
    intensity *= fraction

    intensity = np.clip(intensity, 0, 1, intensity)

    return intensity


def slopeshade(elevation, vert_exag=1, dx=1, dy=1):
    # Calculate the intensity from the illumination angle
    dy, dx = np.gradient(vert_exag * elevation, dy, dx)

    slope = 0.5 * np.pi - np.arctan(np.hypot(dx, dy))

    slope *= (1 / (np.pi / 2))

    return slope


import bisect

# Generate a table of heights suitable for use as hypsometric tinting. These
# have only a little precision for bathymetry, and concentrate most of the
# rest in the 0-3000m range, which is where most of the world's population
# lives.
#
# It seemed better to have this as a function which returned the table rather
# than include the table verbatim, as this would be a big blob of unreadable
# numbers.
def _generate_mapping_table():
    table = []
    for i in range(0, 11):
        table.append(-11000 + i * 1000)
    table.append(-100)
    table.append( -50)
    table.append( -20)
    table.append( -10)
    table.append(  -1)
    for i in range(0, 150):
        table.append(20 * i)
    for i in range(0, 60):
        table.append(3000 + 50 * i)
    for i in range(0, 29):
        table.append(6000 + 100 * i)
    return table


# Make a constant version of the table for reference.
HEIGHT_TABLE = _generate_mapping_table()


# Function which returns the index of the maximum height in the height table
# which is lower than the input `h`. I.e: it rounds down. We then _flip_ the
# table "backwards" so that low heights have higher indices. This is so that
# when it's displayed on a regular computer, the lower values near sea level
# have high alpha, making them more opaque.
def _height_mapping_func(h):
    return 255 - bisect.bisect_left(HEIGHT_TABLE, h)


def render_normal(tile, data, buffers, dx, dy):
    ygrad, xgrad = np.gradient(data, 2)
    img = np.dstack((-1.0 / dx * xgrad, -1.0 / dy * ygrad,
                        np.ones(data.shape)))

    # first, we normalise to unit vectors. this puts each element of img
    # in the range (-1, 1). the "einsum" stuff is serious black magic, but
    # what it (should be) saying is "for each i,j in the rows and columns,
    # the output is the sum of img[i,j,k]*img[i,j,k]" - i.e: the square.
    norm = np.sqrt(np.einsum('ijk,ijk->ij', img, img))

    # the norm is now the "wrong shape" according to numpy, so we need to
    # copy the norm value out into RGB components.
    norm_copy = norm[:, :, np.newaxis]

    # dividing the img by norm_copy should give us RGB components with
    # values between -1 and 1, but we need values between 0 and 255 for
    # PNG channels. so we move and scale the values to fit in that range.
    scaled = (128.0 * (img / norm_copy + 1.0))

    # and finally clip it to (0, 255) just in case
    img = np.clip(scaled, 0.0, 255.0).astype(np.uint8)

    # apply the height mapping function to get the table index.
    func = np.vectorize(_height_mapping_func)
    hyps = func(data).astype(np.uint8)

    # Create output as a 4-channel RGBA image, each (byte) channel
    # corresponds to x, y, z, h where x, y and z are the respective
    # components of the normal, and h is an index into a hypsometric tint
    # table (see HEIGHT_TABLE).
    (left_buffer, bottom_buffer, right_buffer, top_buffer) = buffers
    output = np.dstack((img, hyps))

    return output[left_buffer:output.shape[0] - right_buffer, top_buffer:output.shape[1] - bottom_buffer]
