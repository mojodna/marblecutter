# noqa
# coding=utf-8
from __future__ import absolute_import

from affine import Affine
import mercantile
from rasterio.crs import CRS

from . import render

TILE_SHAPE = (256, 256)
WEB_MERCATOR_CRS = CRS.from_epsg(3857)
WGS84_CRS = CRS.from_epsg(4326)


def render_tile(tile, transformation=None, format="png", scale=1):
    """Render a tile into Web Mercator."""
    bounds = mercantile.bounds(tile)

    shape = Affine.scale(scale) * TILE_SHAPE

    # TODO convert format to an enum

    return render((bounds, WGS84_CRS), shape, WEB_MERCATOR_CRS, format, transformation)
