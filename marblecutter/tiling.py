# coding=utf-8
from __future__ import absolute_import

import logging

import mercantile
from affine import Affine
from rasterio.crs import CRS

from . import Bounds, render

LOG = logging.getLogger(__name__)
TILE_SHAPE = (256, 256)
WEB_MERCATOR_CRS = CRS.from_epsg(3857)
WGS84_CRS = CRS.from_epsg(4326)


def render_tile(tile,
                catalog,
                transformation=None,
                format=None,
                scale=1,
                data_band_count=3):
    """Render a tile into Web Mercator."""
    bounds = Bounds(mercantile.bounds(tile), WGS84_CRS)
    shape = tuple(map(int, Affine.scale(scale) * TILE_SHAPE))

    return render(
        bounds,
        shape,
        WEB_MERCATOR_CRS,
        catalog=catalog,
        format=format,
        data_band_count=data_band_count,
        transformation=transformation)


def render_tile_from_sources(tile,
                             sources,
                             transformation=None,
                             format=None,
                             scale=1,
                             data_band_count=3):
    """Render a tile into Web Mercator."""
    bounds = Bounds(mercantile.bounds(tile), WGS84_CRS)
    shape = tuple(map(int, Affine.scale(scale) * TILE_SHAPE))

    return render(
        bounds,
        shape,
        WEB_MERCATOR_CRS,
        sources=sources,
        format=format,
        data_band_count=data_band_count,
        transformation=transformation)
