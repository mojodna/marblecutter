# coding=utf-8
from __future__ import absolute_import

import logging

from flask import Flask, jsonify
from flask_cors import CORS

from . import InvalidTileRequest, NoCatalogAvailable, NoDataAvailable

LOG = logging.getLogger(__name__)

app = Flask("marblecutter")
app.url_map.strict_slashes = False
CORS(app, send_wildcard=True)


@app.route("/favicon.ico")
def favicon():  # noqa
    return "", 404


@app.errorhandler(InvalidTileRequest)
def handle_invalid_tile_request(error):
    return jsonify(error.to_dict()), 204


@app.errorhandler(NoDataAvailable)
def handle_no_data_available(error):
    return "", 204


@app.errorhandler(NoCatalogAvailable)
def handle_no_catalog_available(error):
    return "", 404


@app.errorhandler(IOError)
def handle_ioerror(error):
    LOG.warn(error)

    return "", 500
