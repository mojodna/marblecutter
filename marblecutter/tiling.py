# noqa
# coding=utf-8
from __future__ import absolute_import

import mercantile
from affine import Affine
from rasterio.crs import CRS

from . import Bounds, render

TILE_SHAPE = (256, 256)
WEB_MERCATOR_CRS = CRS.from_epsg(3857)


def render_tile(tile,
                catalog,
                transformation=None,
                format=None,
                scale=1,
                data_band_count=3):
    """Render a tile into Web Mercator."""
    bounds = mercantile.xy_bounds(tile)

    return render(
        Bounds(bounds, WEB_MERCATOR_CRS),
        catalog,
        tuple(map(int, Affine.scale(scale) * TILE_SHAPE)),
        WEB_MERCATOR_CRS,
        format=format,
        data_band_count=data_band_count,
        transformation=transformation)
