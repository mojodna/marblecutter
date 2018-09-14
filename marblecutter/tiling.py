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


def render_tile(tile, catalog, transformation=None, format=None, scale=1, expand=True):
    """Render a tile into Web Mercator.

    Arguments:
        tile {mercantile.Tile} -- Tile to render.
        catalog {catalogs.Catalog} -- Catalog to load sources from.

    Keyword Arguments:
        transformation {Transformation} -- Transformation to apply. (default: {None})
        format {function} -- Output format. (default: {None})
        scale {int} -- Output scale factor. (default: {1})
        expand {bool} -- Whether to expand single-band, paletted sources to RGBA. (default: {True})

    Returns:
        (dict, bytes) -- Tuple of HTTP headers (dict) and bytes.
    """

    bounds = Bounds(mercantile.xy_bounds(tile), WEB_MERCATOR_CRS)
    shape = tuple(map(int, Affine.scale(scale) * TILE_SHAPE))

    catalog.validate(tile)

    return render(
        bounds,
        shape,
        WEB_MERCATOR_CRS,
        catalog=catalog,
        format=format,
        transformation=transformation,
        expand=expand,
    )


def render_tile_from_sources(
    tile, sources, transformation=None, format=None, scale=1, expand=True
):
    """Render a tile into Web Mercator.

    Arguments:
        tile {mercantile.Tile} -- Tile to render.
        sources {list} -- Sources to render from.

    Keyword Arguments:
        transformation {Transformation} -- Transformation to apply. (default: {None})
        format {function} -- Output format. (default: {None})
        scale {int} -- Output scale factor. (default: {1})
        expand {bool} -- Whether to expand single-band, paletted sources to RGBA. (default: {True})

    Returns:
        (dict, bytes) -- Tuple of HTTP headers (dict) and bytes.
    """
    bounds = Bounds(mercantile.xy_bounds(tile), WEB_MERCATOR_CRS)
    shape = tuple(map(int, Affine.scale(scale) * TILE_SHAPE))

    return render(
        bounds,
        shape,
        WEB_MERCATOR_CRS,
        sources=sources,
        format=format,
        transformation=transformation,
        expand=expand,
    )
