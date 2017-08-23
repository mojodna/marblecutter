# coding=utf-8
from __future__ import absolute_import

import logging

from flask import Flask, jsonify

from flask_cors import CORS

from . import NoDataAvailable

LOG = logging.getLogger(__name__)

app = Flask("marblecutter")
CORS(app, send_wildcard=True)


class InvalidTileRequest(Exception):
    status_code = 404

    def __init__(self, message, status_code=None, payload=None):
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


@app.errorhandler(InvalidTileRequest)
def handle_invalid_tile_request(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code

    return response


@app.errorhandler(NoDataAvailable)
def handle_no_data_available(error):
    return "", 404


@app.errorhandler(IOError)
def handle_ioerror(error):
    LOG.warn(error)

    return "", 500
