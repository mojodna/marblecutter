# noqa
# coding=utf-8
from __future__ import print_function

import logging

import click
from marblecutter import tiling
from marblecutter.catalogs import PostGISCatalog
from marblecutter.formats import PNG, ColorRamp, GeoTIFF
from marblecutter.transformations import Hillshade, Normal, Terrarium
from mercantile import Tile

logging.basicConfig(level=logging.WARNING)

FORMATS = {
    "color-ramp": ColorRamp(),
    "geotiff": GeoTIFF(),
    "png": PNG(),
}
TRANSFORMATIONS = {
    "hillshade": Hillshade(),
    "normal": Normal(),
    "terrarium": Terrarium(),
}


@click.command()
@click.option("-f", "--format", help="Format", default="geotiff")
@click.option(
    "-o", "--output", help="Output file",
    default=click.get_binary_stream("stdout"), type=click.File("wb"))
@click.option("-s", "--scale", help="Scale", default=1, type=float)
@click.option("-t", "--transformation", help="Transformation", default=None)
@click.argument("tile", type=str)
def render_tile(
    format,
    output,
    scale,
    transformation,
    tile,
):
    z, x, y = map(int, tile.split("/"))
    tile = Tile(x, y, z)

    (headers, data) = tiling.render_tile(
        tile,
        PostGISCatalog(),
        format=FORMATS[format],
        transformation=TRANSFORMATIONS.get(transformation),
        scale=scale)

    [click.echo("{}: {}".format(k, v), err=True) for k, v in headers.items()]

    output.write(data)


if __name__ == '__main__':
    render_tile()
