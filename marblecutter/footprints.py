# coding=utf-8
from __future__ import absolute_import

import json

import mercantile
from affine import Affine
from rasterio.crs import CRS

from . import Bounds, get_resolution_in_meters

TILE_SHAPE = (256, 256)
WEB_MERCATOR_CRS = CRS.from_epsg(3857)


def features_for_tile(tile, catalog, scale=1):
    """Render a tile's source footprints."""
    bounds = Bounds(mercantile.xy_bounds(tile), WEB_MERCATOR_CRS)
    shape = tuple(map(int, Affine.scale(scale) * TILE_SHAPE))
    resolution = get_resolution_in_meters(bounds, shape)

    for idx, source in enumerate(
            catalog.get_sources(bounds, resolution, include_geometries=True)):
        yield {
            "type": "Feature",
            # TODO parse JSON in Source
            "geometry": json.loads(source.geom),
            "properties": {
                "index": idx,
                "url": source.url,
                "name": source.name,
                "resolution": source.resolution,
                "band_info": source.band_info,
                "meta": source.meta,
                "recipes": source.recipes,
                "priority": source.priority,
                "coverage": source.coverage,
                "acquired_at": source.acquired_at,
            }
        }


def sources_for_tile(tile, catalog, scale=1):
    """Render a tile's source footprints."""
    bounds = Bounds(mercantile.xy_bounds(tile), WEB_MERCATOR_CRS)
    shape = tuple(map(int, Affine.scale(scale) * TILE_SHAPE))
    resolution = get_resolution_in_meters(bounds, shape)

    for idx, source in enumerate(catalog.get_sources(bounds, resolution)):
        yield {
            "index": idx,
            "url": source.url,
            "name": source.name,
            "resolution": source.resolution,
            "band_info": source.band_info,
            "meta": source.meta,
            "recipes": source.recipes,
            "priority": source.priority,
            "coverage": source.coverage,
            "acquired_at": source.acquired_at,
        }
