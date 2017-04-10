# coding=utf-8

import math
import os
import logging
import urlparse

import arrow
from cachetools.func import rr_cache
from flask import Flask, jsonify, render_template, url_for
from flask_cors import CORS
import mercantile
from mercantile import Tile
from psycopg2.pool import SimpleConnectionPool
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

LOG = logging.getLogger(__name__)

logging.basicConfig()

urlparse.uses_netloc.append('postgres')
database_url = urlparse.urlparse(os.environ['DATABASE_URL'])
pool = SimpleConnectionPool(
    1,
    16,
    database=database_url.path[1:],
    user=database_url.username,
    password=database_url.password,
    host=database_url.hostname,
    port=database_url.port,
)


@app.errorhandler(InvalidTileRequest)
def handle_invalid_tile_request(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


@app.errorhandler(IOError)
def handle_ioerror(error):
    LOG.warn(error)
    return '', 404


@rr_cache()
@app.route('/<int:z>/<int:x>/<int:y>.png')
@app.route('/<int:z>/<int:x>/<int:y>@<int:scale>x.png')
@app.route('/<renderer>/<int:z>/<int:x>/<int:y>.png')
@app.route('/<renderer>/<int:z>/<int:x>/<int:y>@<int:scale>x.png')
def render(z, x, y, scale=1, **kwargs):
    t = Tile(x, y, z)
    bounds = mercantile.bounds(*t)

    y = (bounds[3] + bounds[1]) / 2
    m_per_degree = 111 * 1000
    resolution = (((bounds[2] - bounds[0]) * m_per_degree) / (256 * scale),
                  ((bounds[3] - bounds[1]) * m_per_degree *
                   math.cos(math.radians(y))) / (256 * scale))

    query = """
        SELECT
            DISTINCT(url),
            filename,
            source,
            resolution,
            resolution / {0}
        FROM footprints
        WHERE wkb_geometry && ST_SetSRID('BOX({1} {2}, {3} {4})'::box2d, 4326)
            -- AND (resolution >= {0} OR source = 'ETOPO1')
            -- TODO pull in topobathy before the rest of ned19
            AND (resolution / {0}) BETWEEN 0.5 AND 100
        ORDER BY resolution DESC
    """.format(min(resolution), *bounds)

    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(query)
        meta = {
            'minzoom': 0,
            'maxzoom': 22,
            'bounds': [-180, -85.05113, 180, 85.05113],
            'meta': {
                'sources': [],
            }
        }
        for row in cur.fetchall():
            LOG.warn('scale factor for {}: {}'.format(row[0], row[4]))
            approximate_zoom = min(22, int(math.ceil(
                math.log((2 * math.pi * 6378137) / (row[3] * 256)) /
                math.log(2))))
            meta['meta']['sources'].append({
                'meta': {
                    'approximateZoom': approximate_zoom,
                    'source': os.path.splitext(row[0])[0] + '_warped.vrt',
                    'mask': os.path.splitext(row[0])[0] + '_warped_mask.vrt',
                },
                'bounds': [-180, -85.05113, 180, 85.05113],
            })
    finally:
        pool.putconn(conn)

    tile = read_tile(meta, t, scale=scale, **kwargs)

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
@app.route('/<id>/<int:scene_idx>/<int:z>/<int:x>/<int:y>.png')
@app.route('/<id>/<int:scene_idx>/<int:z>/<int:x>/<int:y>@<int:scale>x.png')
@app.route('/<id>/<int:scene_idx>/<image_id>/<int:z>/<int:x>/<int:y>.png')
@app.route('/<id>/<int:scene_idx>/<image_id>/<int:z>/<int:x>/<int:y>@<int:scale>x.png')
def tile(id, z, x, y, **kwargs):
    meta = get_metadata(id, **kwargs)
    tile = read_tile(meta, Tile(x, y, z), **kwargs)

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
@app.route('/')
@app.route('/<renderer>/')
@app.route('/<id>/<int:scene_idx>/')
@app.route('/<id>/<int:scene_idx>/<image_id>/')
def meta(**kwargs):
    meta = {
        'minzoom': 0,
        'maxzoom': 22,
        'bounds': [-180, -85.05113, 180, 85.05113],
    }

    with app.app_context():
        meta['tiles'] = [
            '{}{{z}}/{{x}}/{{y}}.png'.format(url_for('meta', _external=True, **kwargs))
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


@app.route('/preview')
@app.route('/<renderer>/preview')
@app.route('/<id>/<int:scene_idx>/preview')
@app.route('/<id>/<int:scene_idx>/<image_id>/preview')
def preview(**kwargs):
    with app.app_context():
        return render_template('preview.html', tilejson_url=url_for('meta', _external=True, _scheme='', **kwargs), **kwargs), 200, {
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
