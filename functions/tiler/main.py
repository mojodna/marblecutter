# coding=utf-8

import base64
import collections
import os
import sys

from raven import Client
from werkzeug.routing import NotFound

import app
from app import app as tiler


sentry = Client()


def handle(event, context):
    # TODO populate with request headers + query parameters and use tiler.full_dispatch_request
    # (this forms the basis for a Lambda Flask adapter; perhaps a generic WSGI adapter would be
    # better)
    # see http://werkzeug.pocoo.org/docs/0.11/test/#environment-building
    # see http://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-create-api-as-simple-proxy-for-lambda.html#api-gateway-create-api-as-simple-proxy-for-lambda-test
    with tiler.test_request_context():
        try:
            (endpoint, args) = tiler.url_map.bind("", path_info=event["path"]).match()
        except NotFound:
            return {
                "statusCode": 404,
            }

        try:
            rsp = getattr(app, endpoint)(**args)

            # could bypass this check by properly dispatching (and always receiving a Response)
            if isinstance(rsp, collections.Iterable):
                data = rsp[0] if 0 < len(rsp) else ""
                status_code = rsp[1] if 1 < len(rsp) else 200
                headers = rsp[2] if 2 < len(rsp) else {}
            else:
                data = rsp.get_data()
                status_code = rsp.status_code
                headers = dict(rsp.headers)

            return {
                "statusCode": status_code,
                "headers": headers,
                "body": base64.b64encode(data),
                "isBase64Encoded": True,
            }
        except:
            try:
                rsp = tiler.handle_user_exception(sys.exc_info()[1])

                return {
                    "statusCode": rsp.status_code,
                    "headers": dict(rsp.headers),
                    "body": base64.b64encode(rsp.get_data()),
                    "isBase64Encoded": True,
                }
            except:
                sentry.captureException()
                raise


if __name__ == '__main__':
    print(handle({
        'path': '/57fc935b84ae75bb00ec751b/wmts',
    }, None))

    print(handle({
        'path': '/57fc935b84ae75bb00ec751b/12/1202/1833.png',
    }, None))

    print(handle({
        'path': '/57fc935b84ae75bb00ec751b/12/1202/1833@2px.png',
    }, None))
