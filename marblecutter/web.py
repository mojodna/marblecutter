# coding=utf-8
from __future__ import absolute_import

import logging
import types

from flask import Blueprint, Markup, jsonify, request, render_template
from flask import url_for as _url_for

from . import InvalidTileRequest, NoCatalogAvailable, NoDataAvailable

LOG = logging.getLogger(__name__)

bp = Blueprint("marblecutter", __name__)


def make_prefix():
    host = request.headers.get("X-Forwarded-Host", request.headers.get("Host", ""))

    # sniff for API Gateway
    if ".execute-api." in host and ".amazonaws.com" in host:
        return request.headers.get("X-Stage")


# API Gateway prefix-aware url_for
def url_for(*args, **kwargs):
    return _url_for(*args, __prefix=make_prefix(), **kwargs)


# API Gateway prefix-aware route decorator
def route(self, rule, **options):

    def decorator(f):
        endpoint = options.pop("endpoint", None)
        self.add_url_rule(rule, endpoint, f, **options)
        self.add_url_rule("/<__prefix>" + rule, endpoint, f, **options)
        return f

    return decorator


bp.route = types.MethodType(route, bp)


@bp.route("/favicon.ico")
def favicon():
    return "NOK"


@bp.app_errorhandler(InvalidTileRequest)
def handle_invalid_tile_request(error):
    return jsonify(error.to_dict()), 204


@bp.app_errorhandler(NoDataAvailable)
def handle_no_data_available(error):
    return "", 204


@bp.app_errorhandler(NoCatalogAvailable)
def handle_no_catalog_available(error):
    return "", 404


@bp.app_errorhandler(IOError)
def handle_ioerror(error):
    LOG.exception(error)

    return "", 500
