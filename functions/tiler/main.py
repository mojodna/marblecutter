# coding=utf-8

import os
from os import path
import json
import re

import boto3
from mercantile import Tile
from raven import Client

from tiler import InvalidTileRequest, read_tile


sentry = Client()
S3_BUCKET = os.environ["S3_BUCKET"]
S3 = boto3.resource("s3")
FORMAT = os.environ.get("FORMAT", "png")


def handle(event, context):
    (input_path, ext) = path.splitext(event["path"])
    parts = input_path.split("@")
    input_path = parts.pop(0)

    (y, x, zoom, scene, _) = reversed(input_path.split("/"))
    y = int(y)
    x = int(x)
    zoom = int(zoom)

    if len(parts) > 0:
        scale = int(re.sub(r"[^\d]", "", parts.pop()))
    else:
        scale = 1

    format = ext[1:]

    if format != FORMAT:
        raise InvalidTileRequest("Invalid format")

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
    except InvalidTileRequest:
        raise
    except:
        sentry.captureException()
        raise

    return {
        "statusCode": 302,
        "headers": {
            "Location": "http://{}.s3.amazonaws.com/{}".format(S3_BUCKET, key),
        }
    }
