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

from tiler import InvalidTileRequest, NoDataException, get_metadata, read_tile


APPLICATION_ROOT = os.environ.get('APPLICATION_ROOT', '')
PREFERRED_URL_SCHEME = os.environ.get('PREFERRED_URL_SCHEME', 'http')
SERVER_NAME = os.environ.get('SERVER_NAME', 'localhost:8000')

app = Flask('oam-tiler')
CORS(app)
app.config['APPLICATION_ROOT'] = APPLICATION_ROOT
app.config['PREFERRED_URL_SCHEME'] = PREFERRED_URL_SCHEME
app.config['SERVER_NAME'] = SERVER_NAME

LOG = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO)

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


def get_id(id, image_id=None, scene_idx=0):
    if image_id:
        return '{}/{}/{}'.format(id, scene_idx, image_id)

    return id


@app.errorhandler(InvalidTileRequest)
def handle_invalid_tile_request(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code

    return response


@app.errorhandler(NoDataException)
def handle_response_with_no_data(error):
    response = jsonify({
        'msg': 'No data available for this tile',
    })
    response.status_code = 404

    return response


@app.errorhandler(IOError)
def handle_ioerror(error):
    LOG.warn(error)
    return '', 404


@rr_cache()
@app.route('/<int:z>/<int:x>/<int:y>.<ext>')
@app.route('/<int:z>/<int:x>/<int:y>@<int:scale>x.<ext>')
@app.route('/<renderer>/<int:z>/<int:x>/<int:y>.<ext>')
@app.route('/<renderer>/<int:z>/<int:x>/<int:y>@<int:scale>x.<ext>')
def render(z, x, y, scale=1, **kwargs):
    t = Tile(x, y, z)
    bounds = mercantile.bounds(*t)

    query = """
        SELECT
            DISTINCT(url),
            filename,
            source,
            resolution,
            min_zoom,
            max_zoom,
            priority,
            least(22, ceil(log(2.0, ((2 * pi() * 6378137) / (resolution * 256))::numeric))) approximate_zoom
        FROM footprints
        WHERE wkb_geometry && ST_SetSRID('BOX({1} {2}, {3} {4})'::box2d, 4326)
            AND {0} BETWEEN min_zoom AND max_zoom
            -- AND source != 'ETOPO1'
        ORDER BY PRIORITY DESC, resolution DESC
    """.format(z, *bounds)

    meta = {
        'minzoom': 0,
        'maxzoom': 22,
        'bounds': [-180, -85.05113, 180, 85.05113],
        'meta': {
            'sources': [],
        }
    }

    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(query)

            LOG.warn('%s/%s/%s: %d result(s)', z, x, y, cur.rowcount)

            for row in cur.fetchall():
                meta['meta']['sources'].append({
                    'meta': {
                        'approximateZoom': row[7],
                        'source': os.path.splitext(row[0])[0] + '_warped.vrt',
                        'mask': os.path.splitext(row[0])[0] + '_warped_mask.vrt',
                    },
                    'minzoom': row[4],
                    'maxzoom': row[5],
                    'bounds': [-180, -85.05113, 180, 85.05113],
                })
    finally:
        pool.putconn(conn)

    (content_type, tile) = read_tile(meta, t, scale=scale, **kwargs)

    headers = {
        'Content-Type': content_type,
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
@app.route('/<id>/<int:scene_idx>/<int:z>/<int:x>/<int:y>.<ext>')
@app.route('/<id>/<int:scene_idx>/<int:z>/<int:x>/<int:y>@<int:scale>x.<ext>')
@app.route('/<id>/<int:scene_idx>/<image_id>/<int:z>/<int:x>/<int:y>.<ext>')
@app.route('/<id>/<int:scene_idx>/<image_id>/<int:z>/<int:x>/<int:y>@<int:scale>x.<ext>')
def tile(id, z, x, y, **kwargs):
    meta = get_metadata(id, **kwargs)
    (content_type, tile) = read_tile(meta, Tile(x, y, z), **kwargs)

    headers = {
        'Content-Type': content_type,
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
@app.route('/<renderer>/wmts')
def renderer_wmts(renderer, **kwargs):
    with app.app_context():
        meta = {
            'minzoom': 0,
            'maxzoom': 22,
            'bounds': [-180, -85.05113, 180, 85.05113],
            'name': 'Mapzen Elevation',
            'meta': {}
        }

        # TODO pull the extension and content-type from the renderer module
        return render_template('wmts.xml', id='GeoTIFF', meta=meta, base_url=url_for('meta', renderer=renderer, _external=True, **kwargs), **kwargs), 200, {
            'Content-Type': 'application/xml'
        }


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
