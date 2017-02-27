# coding=utf-8

import os

import awsgi

from app import app as tiler


def handle(event, context):
    # Cloudfront isn't configured to pass Host headers, so the provided Host header is the API Gateway hostname
    event['headers']['Host'] = os.environ['SERVER_NAME']
    # Cloudfront drops X-Forwarded-Proto, so the value provided is from API Gateway
    event['headers']['X-Forwarded-Proto'] = 'http'
    return awsgi.response(tiler, event, context)


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
