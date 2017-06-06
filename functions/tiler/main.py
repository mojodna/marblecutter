# noqa
# coding=utf-8

import logging
import os

import awsgi
from marblecutter.web import app


# reset the Lambda logger
root = logging.getLogger()
if root.handlers:
    for handler in root.handlers:
        root.removeHandler(handler)

logging.basicConfig(level=logging.INFO)


def handle(event, context): # noqa
    # Cloudfront isn't configured to pass Host headers, so the provided Host
    # header is the API Gateway hostname
    event['headers']['Host'] = os.environ['SERVER_NAME']
    # Cloudfront drops X-Forwarded-Proto, so the value provided is from API
    # Gateway
    event['headers']['X-Forwarded-Proto'] = 'http'

    return awsgi.response(app, event, context)
