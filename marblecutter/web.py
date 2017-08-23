# noqa
# coding=utf-8
from __future__ import absolute_import

import logging
import os

from cachetools.func import lru_cache
from flask import Flask, jsonify, render_template, request, url_for
from mercantile import Tile

from flask_cors import CORS

from . import NoDataAvailable, tiling
from .catalogs import OAMSceneCatalog, OINMetaCatalog
from .formats import PNG
from .transformations import Image

LOG = logging.getLogger(__name__)

app = Flask("marblecutter")
CORS(app, send_wildcard=True)

app.config["PREFERRED_URL_SCHEME"] = os.getenv("PREFERRED_URL_SCHEME", "http")

IMAGE_TRANSFORMATION = Image()
PNG_FORMAT = PNG()


class InvalidTileRequest(Exception):  # noqa
    status_code = 404

    def __init__(self, message, status_code=None, payload=None):  # noqa
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):  # noqa
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv


@app.route("/favicon.ico")
def favicon():  # noqa
    return '', 404


S3_BUCKET = "oin-hotosm"


@lru_cache()
def make_catalog(scene_id, scene_idx, image_id=None):
    if image_id:
        return OINMetaCatalog("https://{}.s3.amazonaws.com/{}/{}/{}_meta.json".
                              format(S3_BUCKET, scene_id, scene_idx, image_id))

    return OAMSceneCatalog("https://{}.s3.amazonaws.com/{}/{}/scene.json".
                           format(S3_BUCKET, scene_id, scene_idx))


@app.route('/<prefix>/<id>/<int:scene_idx>/')
@app.route('/<id>/<int:scene_idx>/')
@app.route('/<prefix>/<id>/<int:scene_idx>/<image_id>/')
@app.route('/<id>/<int:scene_idx>/<image_id>/')
def meta_oam(id, scene_idx, image_id=None, **kwargs):
    catalog = make_catalog(id, scene_idx, image_id)

    meta = {
        "bounds": catalog.bounds,
        "center": catalog.center,
        "maxzoom": catalog.maxzoom,
        "minzoom": catalog.minzoom,
        "name": catalog.name,
        "tilejson": "2.1.0",
    }

    with app.app_context():
        meta["tiles"] = [
            "{}{{z}}/{{x}}/{{y}}.png".format(
                url_for(
                    "meta_oam",
                    id=id,
                    scene_idx=scene_idx,
                    image_id=image_id,
                    prefix=request.headers.get("X-Stage"),
                    _external=True,
                    _scheme=""))
        ]

    return jsonify(meta)


@app.route('/<prefix>/<id>/<int:scene_idx>/wmts')
@app.route('/<id>/<int:scene_idx>/wmts')
@app.route('/<prefix>/<id>/<int:scene_idx>/<image_id>/wmts')
@app.route('/<id>/<int:scene_idx>/<image_id>/wmts')
def wmts(id, scene_idx, image_id=None, **kwargs):
    catalog = make_catalog(id, scene_idx, image_id)

    provider = "OpenAerialMap"
    provider_url = "https://openaerialmap.org/"

    if catalog.provider:
        provider = "{} ({})".format(provider, catalog.provider)

    with app.app_context():
        base_url = url_for(
            "meta_oam",
            id=id,
            scene_idx=scene_idx,
            image_id=image_id,
            prefix=request.headers.get("X-Stage"),
            _external=True)

        return render_template(
            'wmts.xml',
            base_url=base_url,
            bounds=catalog.bounds,
            content_type="image/png",
            ext="png",
            id=catalog.id,
            maxzoom=catalog.maxzoom,
            metadata_url=catalog.metadata_url,
            minzoom=catalog.minzoom,
            provider=provider,
            provider_url=provider_url,
            title=catalog.name,
            ), 200, {
            'Content-Type': 'application/xml'
        }


@app.route('/<prefix>/<id>/<int:scene_idx>/preview')
@app.route('/<id>/<int:scene_idx>/preview')
@app.route('/<prefix>/<id>/<int:scene_idx>/<image_id>/preview')
@app.route('/<id>/<int:scene_idx>/<image_id>/preview')
def preview_oam(id, scene_idx, image_id=None, **kwargs):
    # load the catalog so it will fail if the source doesn't exist
    make_catalog(id, scene_idx, image_id)

    with app.app_context():
        return render_template(
            "preview.html",
            tilejson_url=url_for(
                "meta_oam",
                id=id,
                scene_idx=scene_idx,
                image_id=image_id,
                prefix=request.headers.get("X-Stage"),
                _external=True,
                _scheme="")), 200, {
                    "Content-Type": "text/html"
                }


@app.route('/<prefix>/<id>/<int:scene_idx>/<int:z>/<int:x>/<int:y>.png')
@app.route('/<id>/<int:scene_idx>/<int:z>/<int:x>/<int:y>.png')
@app.route('/<prefix>/<id>/<int:scene_idx>/<int:z>/<int:x>/<int:y>@<int:scale>x.png')
@app.route('/<id>/<int:scene_idx>/<int:z>/<int:x>/<int:y>@<int:scale>x.png')
@app.route('/<prefix>/<id>/<int:scene_idx>/<image_id>/<int:z>/<int:x>/<int:y>.png')
@app.route('/<id>/<int:scene_idx>/<image_id>/<int:z>/<int:x>/<int:y>.png')
@app.route(
    '/<prefix>/<id>/<int:scene_idx>/<image_id>/<int:z>/<int:x>/<int:y>@<int:scale>x.png'
)
@app.route(
    '/<id>/<int:scene_idx>/<image_id>/<int:z>/<int:x>/<int:y>@<int:scale>x.png'
)
def render_oam(id, scene_idx, z, x, y, image_id=None, scale=1, **kwargs):  # noqa
    tile = Tile(x, y, z)

    headers, data = tiling.render_tile(
        tile,
        make_catalog(id, scene_idx, image_id),
        format=PNG_FORMAT,
        transformation=IMAGE_TRANSFORMATION,
        scale=scale)

    return data, 200, headers


@app.errorhandler(InvalidTileRequest)
def handle_invalid_tile_request(error):  # noqa
    response = jsonify(error.to_dict())
    response.status_code = error.status_code

    return response


@app.errorhandler(NoDataAvailable)
def handle_no_data_available(error):  # noqa
    return "", 404


@app.errorhandler(IOError)
def handle_ioerror(error):  # noqa
    LOG.warn(error)

    return "", 500


static = app.send_static_file
