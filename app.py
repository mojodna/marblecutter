# noqa
# coding=utf-8

from __future__ import division

import os
import logging
import re
import urlparse

import arrow
from cachetools.func import rr_cache
from flask import Flask, jsonify, render_template, url_for
from flask_cors import CORS
import mercantile
from mercantile import Tile
from psycopg2.pool import SimpleConnectionPool
from werkzeug.wsgi import DispatcherMiddleware

from tiler import (
    InvalidTileRequest,
    NoDataException,
    get_metadata,
    get_renderer,
    get_source,
    make_window2,
    read_tile,
)


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

urlparse.uses_netloc.append('postgis')
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


def get_id(id, image_id=None, scene_idx=0): # noqa
    if image_id:
        return '{}/{}/{}'.format(id, scene_idx, image_id)

    return id


@app.errorhandler(InvalidTileRequest)
def handle_invalid_tile_request(error): # noqa
    response = jsonify(error.to_dict())
    response.status_code = error.status_code

    return response


@app.errorhandler(NoDataException)
def handle_response_with_no_data(error): # noqa
    response = jsonify({
        'msg': 'No data available for this tile',
    })
    response.status_code = 404

    return response


@app.errorhandler(IOError)
def handle_ioerror(error): # noqa
    LOG.warn('IOError')
    LOG.warn(error)
    return '', 500


HALF_ARC_SEC = (1.0/3600.0)*.5

def _bbox(x, y):
    return (
        (x - 180) - HALF_ARC_SEC,
        (y - 90) - HALF_ARC_SEC,
        (x - 179) + HALF_ARC_SEC,
        (y - 89) + HALF_ARC_SEC)


SKADI_TILE_NAME_PATTERN = re.compile('^([NS])([0-9]{2})([EW])([0-9]{3})$')
def _parse_skadi_tile(tile_name):
    m = SKADI_TILE_NAME_PATTERN.match(tile_name)
    if m:
        y = int(m.group(2))
        x = int(m.group(4))
        if m.group(1) == 'S':
            y = -y
        if m.group(3) == 'W':
            x = -x
        return (x + 180, y + 90)
    return None


@app.route('/skadi/<_>/<tile>.hgt.gz')
def render_skadi(_, tile): # noqa
    LOG.warn('tile: %s', tile)
    (x, y) = _parse_skadi_tile(tile)

    LOG.warn('x: %f, y: %f', x, y)

    bounds = _bbox(x, y)

    LOG.warn('bbox: %s', bounds)

    query = """
        SELECT
            DISTINCT(url),
            filename,
            source,
            resolution,
            min_zoom,
            max_zoom,
            priority,
            approximate_zoom
        FROM footprints
        WHERE wkb_geometry && ST_SetSRID('BOX({0} {1}, {2} {3})'::box2d, 4326)
        ORDER BY PRIORITY DESC, resolution DESC
    """.format(*bounds)

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

            for row in cur.fetchall():
                LOG.warn('source: %s: %s', row[2], row[0])

                src = get_source(row[0])
                # window = make_window2(bounds, {'init': 'EPSG:4326'}, src.crs, src.transform, dst_shape=(3601, 3601))
                #
                # LOG.warn('window: %s', window)

                meta['meta']['sources'].append({
                    'meta': {
                        'approximateZoom': row[7],
                        'source': '{}_warped.vrt'.format(
                            os.path.splitext(row[0])[0]),
                        'mask': '{}_warped_mask.vrt'.format(
                            os.path.splitext(row[0])[0]),
                    },
                    'minzoom': row[4],
                    'maxzoom': row[5],
                    'bounds': [-180, -85.05113, 180, 85.05113],
                })
    finally:
        pool.putconn(conn)

    return '', 200

@app.route('/<renderer>/<int:z>/<int:x>/<int:y>.<ext>')
@app.route('/<renderer>/<int:z>/<int:x>/<int:y>@<int:scale>x.<ext>')
def render(renderer, z, x, y, ext, scale=1, **kwargs): # noqa
    render_module = get_renderer(renderer)

    if ext != render_module.EXT:
        raise InvalidTileRequest('Invalid format; should be {}'.format(
            render_module.EXT))

    t = Tile(x, y, z)
    buffer = getattr(render_module, 'BUFFER', 0)

    bounds = list(mercantile.bounds(*t))

    pixel_width = (bounds[2] - bounds[0]) / 256
    pixel_height = (bounds[3] - bounds[1]) / 256

    # buffer bounds enough to cover <buffer> pixels
    bounds[0] -= pixel_width * buffer
    bounds[1] -= pixel_height * buffer
    bounds[2] += pixel_width * buffer
    bounds[3] += pixel_height * buffer

    # TODO refactor to generate tuples of bounds (usually 1, but possibly 2 to handle antimeridian discontinuities; this will help in the future when rendering arbitrary bboxes covering the antimeridian)
    # https://github.com/fortyninemaps/picogeojson/blob/master/picogeojson/antimeridian.py

    query = """
        SELECT
            DISTINCT(url),
            filename,
            source,
            resolution,
            min_zoom,
            max_zoom,
            priority,
            approximate_zoom
        FROM footprints
        WHERE wkb_geometry && ST_SetSRID('BOX({1} {2}, {3} {4})'::box2d, 4326)
            AND {0} BETWEEN min_zoom AND max_zoom
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
                        'source': '{}_warped.vrt'.format(
                            os.path.splitext(row[0])[0]),
                        'mask': '{}_warped_mask.vrt'.format(
                            os.path.splitext(row[0])[0]),
                    },
                    'minzoom': row[4],
                    'maxzoom': row[5],
                    'bounds': [-180, -85.05113, 180, 85.05113],
                })
    finally:
        pool.putconn(conn)

    (content_type, tile) = read_tile(
        meta,
        t,
        renderer=renderer,
        scale=scale,
        **kwargs
    )

    headers = {
        'Content-Type': content_type,
    }

    if meta['meta'].get('oinMetadataUrl'):
        headers['X-OIN-Metadata-URL'] = meta['meta'].get('oinMetadataUrl')

    if meta['meta'].get('acquisitionStart') or \
       meta['meta'].get('acquisitionEnd'):
        start = meta['meta'].get('acquisitionStart')
        end = meta['meta'].get('acquisitionEnd')

        if start and end:
            start = arrow.get(start)
            end = arrow.get(end)

            capture_range = '{}-{}'.format(
                start.format('M/D/YYYY'), end.format('M/D/YYYY'))
            headers['X-OIN-Acquisition-Start'] = start.format(
                'YYYY-MM-DDTHH:mm:ssZZ')
            headers['X-OIN-Acquisition-End'] = end.format(
                'YYYY-MM-DDTHH:mm:ssZZ')
        elif start:
            start = arrow.get(start)

            capture_range = start.format('M/D/YYYY')
            headers['X-OIN-Acquisition-Start'] = start.format(
                'YYYY-MM-DDTHH:mm:ssZZ')
        elif end:
            end = arrow.get(end)

            capture_range = end.format('M/D/YYYY')
            headers['X-OIN-Acquisition-End'] = end.format(
                'YYYY-MM-DDTHH:mm:ssZZ')

        # Bing Maps-compatibility (JOSM uses this)
        headers['X-VE-TILEMETA-CaptureDatesRange'] = capture_range

    if meta['meta'].get('provider'):
        headers['X-OIN-Provider'] = meta['meta'].get('provider')

    if meta['meta'].get('platform'):
        headers['X-OIN-Platform'] = meta['meta'].get('platform')

    return tile, 200, headers


@app.route('/<id>/<int:scene_idx>/<int:z>/<int:x>/<int:y>.<ext>')
@app.route('/<id>/<int:scene_idx>/<int:z>/<int:x>/<int:y>@<int:scale>x.<ext>')
@app.route('/<id>/<int:scene_idx>/<image_id>/<int:z>/<int:x>/<int:y>.<ext>')
@app.route('/<id>/<int:scene_idx>/<image_id>/<int:z>/<int:x>/<int:y>@<int:scale>x.<ext>')
def tile(id, z, x, y, **kwargs): # noqa
    meta = get_metadata(id, **kwargs)
    (content_type, tile) = read_tile(meta, Tile(x, y, z), **kwargs)

    headers = {
        'Content-Type': content_type,
    }

    if meta['meta'].get('oinMetadataUrl'):
        headers['X-OIN-Metadata-URL'] = meta['meta'].get('oinMetadataUrl')

    if meta['meta'].get('acquisitionStart') or \
       meta['meta'].get('acquisitionEnd'):
        start = meta['meta'].get('acquisitionStart')
        end = meta['meta'].get('acquisitionEnd')

        if start and end:
            start = arrow.get(start)
            end = arrow.get(end)

            capture_range = '{}-{}'.format(
                start.format('M/D/YYYY'), end.format('M/D/YYYY'))
            headers['X-OIN-Acquisition-Start'] = start.format(
                'YYYY-MM-DDTHH:mm:ssZZ')
            headers['X-OIN-Acquisition-End'] = end.format(
                'YYYY-MM-DDTHH:mm:ssZZ')
        elif start:
            start = arrow.get(start)

            capture_range = start.format('M/D/YYYY')
            headers['X-OIN-Acquisition-Start'] = start.format(
                'YYYY-MM-DDTHH:mm:ssZZ')
        elif end:
            end = arrow.get(end)

            capture_range = end.format('M/D/YYYY')
            headers['X-OIN-Acquisition-End'] = end.format(
                'YYYY-MM-DDTHH:mm:ssZZ')

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
def meta(**kwargs): # noqa
    meta = {
        'minzoom': 0,
        'maxzoom': 22,
        'bounds': [-180, -85.05113, 180, 85.05113],
    }

    with app.app_context():
        meta['tiles'] = [
            '{}{{z}}/{{x}}/{{y}}.png'.format(
                url_for('meta', _external=True, **kwargs))
        ]

    return jsonify(meta)


@rr_cache()
@app.route('/<renderer>/wmts')
def renderer_wmts(renderer, **kwargs): # noqa
    render_module = get_renderer(renderer)

    with app.app_context():
        meta = {
            'minzoom': 0,
            'maxzoom': 22,
            'bounds': [-180, -85.05113, 180, 85.05113],
            'name': 'Mapzen Elevation',
            'meta': {}
        }

        # TODO pull the extension and content-type from the renderer module
        return render_template(
            'wmts.xml',
            content_type=render_module.CONTENT_TYPE,
            ext=render_module.EXT,
            id=render_module.NAME,
            meta=meta,
            base_url=url_for(
                'meta',
                renderer=renderer,
                _external=True,
                **kwargs
            ), **kwargs
        ), 200, {
            'Content-Type': 'application/xml'
        }


@rr_cache()
@app.route('/<id>/<int:scene_idx>/wmts')
@app.route('/<id>/<int:scene_idx>/<image_id>/wmts')
def wmts(id, **kwargs): # noqa
    with app.app_context():
        return render_template(
            'wmts.xml',
            id=get_id(id, **kwargs),
            meta=get_metadata(id, **kwargs),
            base_url=url_for(
                'meta',
                id=id,
                _external=True,
                **kwargs
            ), **kwargs
        ), 200, {
            'Content-Type': 'application/xml'
        }


@app.route('/preview')
@app.route('/<renderer>/preview')
@app.route('/<id>/<int:scene_idx>/preview')
@app.route('/<id>/<int:scene_idx>/<image_id>/preview')
def preview(**kwargs): # noqa
    with app.app_context():
        return render_template(
            'preview.html',
            tilejson_url=url_for(
                'meta',
                _external=True,
                _scheme='',
                **kwargs
            ),
            **kwargs
        ), 200, {
            'Content-Type': 'text/html'
        }


@app.route('/favicon.ico')
def favicon(): # noqa
    return '', 404


static = app.send_static_file


app.wsgi_app = DispatcherMiddleware(None, {
    app.config['APPLICATION_ROOT']: app.wsgi_app
})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
