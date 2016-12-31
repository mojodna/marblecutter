# coding=utf-8

from StringIO import StringIO
import os

from cachetools.func import lru_cache
import mercantile
import numpy as np
from PIL import Image
import rasterio
import requests


S3_BUCKET = os.environ["S3_BUCKET"]


@lru_cache()
def get_metadata(id):
    return requests.get('https://s3.amazonaws.com/{}/sources/{}/index.json'.format(S3_BUCKET, id)).json()

@lru_cache()
def get_source(path):
    with rasterio.Env():
        return rasterio.open(path)


def render_tile(meta, tile, scale=1):
    src_tile_zoom = meta['meta']['approximateZoom']
    src_url = meta['meta']['source']
    # do calculations in src_tile_zoom space
    dz = src_tile_zoom - tile.z
    x = 2**dz * tile.x
    y = 2**dz * tile.y
    mx = 2**dz * (tile.x + 1)
    my = 2**dz * (tile.y + 1)
    dx = mx - x
    dy = my - y
    top = (2**src_tile_zoom * 256) - 1

    # y, x (rows, columns)
    # window is measured in pixels at src_tile_zoom
    window = [[top - (top - (256 * y)), top - (top - ((256 * y) + int(256 * dy)))],
              [256 * x, (256 * x) + int(256 * dx)]]

    src = get_source(src_url)
    # use decimated reads to read from overviews, per https://github.com/mapbox/rasterio/issues/710
    data = np.empty(shape=(4, 256 * scale, 256 * scale)).astype(src.profile['dtype'])
    data = src.read(out=data, window=window)

    return data


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


def get_bounds(id):
    return get_metadata(id)['bounds']


def read_tile(id, tile, scale=1):
    meta = get_metadata(id)
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

    data = render_tile(meta, tile, scale=scale)
    imgarr = np.ma.transpose(data, [1, 2, 0]).astype(np.byte)

    out = StringIO()
    im = Image.fromarray(imgarr, 'RGBA')
    im.save(out, 'png')

    return out.getvalue()
