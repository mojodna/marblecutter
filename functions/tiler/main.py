# coding=utf-8

import os
from os import path
import json
import re

import boto3
from jinja2 import Template
from mercantile import Tile
from raven import Client
from werkzeug.routing import Map, NotFound, Rule

from tiler import InvalidTileRequest, get_metadata, read_tile


sentry = Client()
S3_BUCKET = os.environ["S3_BUCKET"]
S3 = boto3.resource("s3")
FORMAT = os.environ.get("FORMAT", "png")
WMTS_TEMPLATE = Template(open("templates/wmts.xml", "r").read())


routes = Map([
    Rule("/<scene>/wmts", endpoint="wmts"),
    Rule("/<scene>/<int:zoom>/<int:x>/<int:y>.{}".format(FORMAT), endpoint="tile"),
    Rule("/<scene>/<int:zoom>/<int:x>/<int:y>@<int:scale>x.{}".format(FORMAT), endpoint="tile"),
])


def tile(scene, zoom, x, y, scale=1, **kwargs):
    try:
        tile = Tile(x, y, zoom)
        data = read_tile(scene, tile, scale=scale)

        if scale == 1:
            key = "{}/{}/{}/{}.{}".format(scene, tile.z, tile.x, tile.y, FORMAT)

            S3.Object(
                S3_BUCKET,
                key,
            ).put(
                Body=data,
                ACL="public-read",
                ContentType="image/{}".format(FORMAT),
                CacheControl="public, max-age=2592000",
                StorageClass="REDUCED_REDUNDANCY",
            )
        elif scale == 2:
            key = "{}/{}/{}/{}@2x.{}".format(scene, tile.z, tile.x, tile.y, FORMAT)

            S3.Object(
                S3_BUCKET,
                key,
            ).put(
                Body=data,
                ACL="public-read",
                ContentType="image/{}".format(FORMAT),
                CacheControl="public, max-age=2592000",
                StorageClass="REDUCED_REDUNDANCY",
            )
    except InvalidTileRequest as error:
        return {
            "statusCode": error.status_code,
            "headers": {
                "Content-Type": "application/json",
            },
            "body": json.dumps(error.to_dict()),
        }

    return {
        "statusCode": 302,
        "headers": {
            "Location": "http://{}.s3.amazonaws.com/{}".format(S3_BUCKET, key),
        }
    }


def wmts(scene, **kwargs):
    data = WMTS_TEMPLATE.render(
        base_url="http://{}.s3-website-us-east-1.amazonaws.com/{}".format(S3_BUCKET, scene),
        bounds=get_metadata(scene)["bounds"],
        id=scene,
    )

    S3.Object(
        S3_BUCKET,
        "{}/wmts".format(scene),
    ).put(
        Body=data,
        ACL="public-read",
        ContentType="application/xml",
        CacheControl="public, max-age=2592000",
        StorageClass="REDUCED_REDUNDANCY",
    )

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/xml",
        },
        "body": data,
    }


def handle(event, context):
    try:
        (endpoint, args) = routes.bind("", path_info=event["path"]).match()
        scale = args.get('scale', 1)
    except NotFound:
        return {
            "statusCode": 404,
        }

    try:
        return globals()[endpoint](**args)
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
