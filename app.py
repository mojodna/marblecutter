# coding=utf-8

import os
import logging

from cachetools.func import rr_cache
from flask import Flask, jsonify, render_template, url_for
from flask_cors import CORS
from mercantile import Tile
from werkzeug.wsgi import DispatcherMiddleware

from tiler import InvalidTileRequest, get_bounds, get_metadata, read_tile


APPLICATION_ROOT = os.environ.get('APPLICATION_ROOT', '')
PREFERRED_URL_SCHEME = os.environ.get('PREFERRED_URL_SCHEME', 'http')
SERVER_NAME = os.environ.get('SERVER_NAME', 'localhost:8000')

app = Flask('oam-tiler')
CORS(app)
app.config['APPLICATION_ROOT'] = APPLICATION_ROOT
app.config['PREFERRED_URL_SCHEME'] = PREFERRED_URL_SCHEME
app.config['SERVER_NAME'] = SERVER_NAME


@app.errorhandler(InvalidTileRequest)
def handle_invalid_tile_request(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


@app.errorhandler(IOError)
def handle_ioerror(error):
    logging.warn(error)
    return '', 404


@rr_cache()
@app.route('/<id>/<int:scene_idx>/<int:z>/<int:x>/<int:y>.png')
def get_tile_from_scene(id, z, x, y, **kwargs):
    tile = read_tile(id, Tile(x, y, z), **kwargs)

    return tile, 200, {
        'Content-Type': 'image/png'
    }


@rr_cache()
@app.route('/<id>/<int:scene_idx>/<int:z>/<int:x>/<int:y>@<int:scale>x.png')
def get_scaled_tile_from_scene(id, z, x, y, scale, **kwargs):
    tile = read_tile(id, Tile(x, y, z), scale=scale, **kwargs)

    return tile, 200, {
        'Content-Type': 'image/png'
    }


@rr_cache()
@app.route('/<id>/<int:scene_idx>/<image_id>/<int:z>/<int:x>/<int:y>.png')
def get_tile(id, z, x, y, **kwargs):
    tile = read_tile(id, Tile(x, y, z), **kwargs)

    return tile, 200, {
        'Content-Type': 'image/png'
    }


@rr_cache()
@app.route('/<id>/<int:scene_idx>/<image_id>/<int:z>/<int:x>/<int:y>@<int:scale>x.png')
def get_scaled_tile(id, z, x, y, scale, **kwargs):
    tile = read_tile(id, Tile(x, y, z), scale=scale, **kwargs)

    return tile, 200, {
        'Content-Type': 'image/png'
    }


@rr_cache()
@app.route('/<id>/<int:scene_idx>')
def scene_meta(id, **kwargs):
    # TODO add tiles[] to form actionable TileJSON
    return jsonify(get_metadata(id, **kwargs))


@rr_cache()
@app.route('/<id>/<int:scene_idx>/<image_id>')
def meta(id, **kwargs):
    # TODO add tiles[] to form actionable TileJSON
    return jsonify(get_metadata(id, **kwargs))


@rr_cache()
@app.route('/<id>/<int:scene_idx>/wmts')
def scene_wmts(id, **kwargs):
    with app.app_context():
        return render_template('wmts.xml', id=id, bounds=get_bounds(id, **kwargs), base_url=url_for('scene_meta', id=id, _external=True, **kwargs), **kwargs), 200, {
            'Content-Type': 'application/xml'
        }


@rr_cache()
@app.route('/<id>/<int:scene_idx>/<image_id>/wmts')
def wmts(id, **kwargs):
    with app.app_context():
        return render_template('wmts.xml', id=id, bounds=get_bounds(id, **kwargs), base_url=url_for('meta', id=id, _external=True, **kwargs), **kwargs), 200, {
            'Content-Type': 'application/xml'
        }


@app.route('/favicon.ico')
def favicon():
    return '', 404


app.wsgi_app = DispatcherMiddleware(None, {
    app.config['APPLICATION_ROOT']: app.wsgi_app
})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
