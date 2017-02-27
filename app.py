# coding=utf-8

import os
import logging

import arrow
from cachetools.func import rr_cache
from flask import Flask, jsonify, render_template, url_for
from flask_cors import CORS
from mercantile import Tile
from werkzeug.wsgi import DispatcherMiddleware

from tiler import InvalidTileRequest, get_id, get_metadata, read_tile


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
@app.route('/<id>/<int:scene_idx>/<int:z>/<int:x>/<int:y>@<int:scale>x.png')
@app.route('/<id>/<int:scene_idx>/<image_id>/<int:z>/<int:x>/<int:y>.png')
@app.route('/<id>/<int:scene_idx>/<image_id>/<int:z>/<int:x>/<int:y>@<int:scale>x.png')
def tile(id, z, x, y, **kwargs):
    meta = get_metadata(id, **kwargs)
    tile = read_tile(id, Tile(x, y, z), **kwargs)

    headers = {
        'Content-Type': 'image/png',
    }

    if meta['meta'].get('oinMetadataUrl'):
        headers['X-OIN-Metadata-URL'] = meta['meta'].get('oinMetadataUrl')

    if meta['meta'].get('acquisitionStart') or meta['meta'].get('acquisitionEnd'):
        start = meta['meta'].get('acquisitionStart')
        end = meta['meta'].get('acquisitionEnd')

        if start and end:
            start = arrow.get(start)
            end = arrow.get(end)

            capture_range = '{}-{}'.format(start.format('M/D/YYYY'), end.format('M/D/YYYY'))
            headers['X-OIN-Acquisition-Start'] = start.format('YYYY-MM-DDTHH:mm:ssZZ')
            headers['X-OIN-Acquisition-End'] = end.format('YYYY-MM-DDTHH:mm:ssZZ')
        elif start:
            start = arrow.get(start)

            capture_range = start.format('M/D/YYYY')
            headers['X-OIN-Acquisition-Start'] = start.format('YYYY-MM-DDTHH:mm:ssZZ')
        elif end:
            end = arrow.get(end)

            capture_range = end.format('M/D/YYYY')
            headers['X-OIN-Acquisition-End'] = end.format('YYYY-MM-DDTHH:mm:ssZZ')

        # Bing Maps-compatibility (JOSM uses this)
        headers['X-VE-TILEMETA-CaptureDatesRange'] = capture_range

    if meta['meta'].get('provider'):
        headers['X-OIN-Provider'] = meta['meta'].get('provider')

    if meta['meta'].get('platform'):
        headers['X-OIN-Platform'] = meta['meta'].get('platform')

    return tile, 200, headers


@rr_cache()
@app.route('/<id>/<int:scene_idx>')
@app.route('/<id>/<int:scene_idx>/<image_id>')
def meta(id, **kwargs):
    meta = get_metadata(id, **kwargs)

    with app.app_context():
        meta['tiles'] = [
            '{}/{{z}}/{{x}}/{{y}}.png'.format(url_for('meta', id=id, _external=True, **kwargs))
        ]

    return jsonify(meta)


@rr_cache()
@app.route('/<id>/<int:scene_idx>/wmts')
@app.route('/<id>/<int:scene_idx>/<image_id>/wmts')
def wmts(id, **kwargs):
    with app.app_context():
        return render_template('wmts.xml', id=get_id(id, **kwargs), meta=get_metadata(id, **kwargs), base_url=url_for('meta', id=id, _external=True, **kwargs), **kwargs), 200, {
            'Content-Type': 'application/xml'
        }


@app.route('/<id>/<int:scene_idx>/preview')
@app.route('/<id>/<int:scene_idx>/<image_id>/preview')
def preview(id, **kwargs):
    with app.app_context():
        return render_template('preview.html', tilejson_url=url_for('meta', id=id, _external=True, _scheme='', **kwargs), **kwargs), 200, {
            'Content-Type': 'text/html'
        }


@app.route('/favicon.ico')
def favicon():
    return '', 404


static = app.send_static_file


app.wsgi_app = DispatcherMiddleware(None, {
    app.config['APPLICATION_ROOT']: app.wsgi_app
})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
