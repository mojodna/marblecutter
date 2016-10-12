# coding=utf-8

from StringIO import StringIO
import os

from cachetools.func import lru_cache, rr_cache
from flask import Flask, jsonify
from flask_cors import CORS
import mercantile
from mercantile import Tile
import numpy as np
from PIL import Image
import rasterio
import requests
from werkzeug.wsgi import DispatcherMiddleware


APPLICATION_ROOT = os.environ.get('APPLICATION_ROOT', '')
MIN_ZOOM = int(os.environ.get('MIN_ZOOM', 0))
MAX_ZOOM = int(os.environ.get('MAX_ZOOM', 22))

app = Flask('oam-tiler')
CORS(app)
app.config['APPLICATION_ROOT'] = APPLICATION_ROOT


@lru_cache()
def get_metadata(id):
    return requests.get('https://s3.amazonaws.com/oam-dynamic-tiler-tmp/uploads/2016-10-11/57fca69e84ae75bb00ec751f/scene/0/scene-0-image-0-DG-103001005E85AC00.json').json()

    return meta

@lru_cache()
def get_source(path):
    with rasterio.drivers():
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


def read_tile(id, tile, scale=1):
    meta = get_metadata(id)

    # TODO limit to some number of zooms beneath approximateZoom
    if not meta['meta']['approximateZoom'] - 5 <= tile.z <= MAX_ZOOM:
        raise InvalidTileRequest('Invalid zoom: {} outside [{}, {}]'.format(tile.z, meta['meta']['approximateZoom'] - 5, MAX_ZOOM))

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


@app.errorhandler(InvalidTileRequest)
def handle_invalid_tile_request(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


@app.errorhandler(IOError)
def handle_ioerror(error):
    return '', 404


@rr_cache()
@app.route('/<id>/<int:z>/<int:x>/<int:y>.png')
def get_tile(id, z, x, y):
    tile = read_tile(id, Tile(x, y, z))

    return tile, 200, {
        'Content-Type': 'image/png'
    }


@rr_cache()
@app.route('/<id>/<int:z>/<int:x>/<int:y>@<int:scale>x.png')
def get_scaled_tile(id, z, x, y, scale):
    tile = read_tile(id, Tile(x, y, z), scale=scale)

    return tile, 200, {
        'Content-Type': 'image/png'
    }


app.wsgi_app = DispatcherMiddleware(None, {
    app.config['APPLICATION_ROOT']: app.wsgi_app
})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
