# noqa
# coding=utf-8
from __future__ import absolute_import

import mercantile
from affine import Affine
from rasterio.crs import CRS

from . import render

TILE_SHAPE = (256, 256)
WEB_MERCATOR_CRS = CRS.from_epsg(3857)


def render_tile(tile,
                sources,
                transformation=None,
                format=None,
                scale=1):
    """Render a tile into Web Mercator."""
    bounds = mercantile.xy_bounds(tile)

    return render(
        (bounds, WEB_MERCATOR_CRS),
        sources,
        map(int, Affine.scale(scale) * TILE_SHAPE),
        WEB_MERCATOR_CRS,
        format=format,
        transformation=transformation)
