# coding=utf-8
from __future__ import absolute_import

import logging

import mercantile
from affine import Affine
from rasterio.crs import CRS

from . import Bounds, get_resolution_in_meters

LOG = logging.getLogger(__name__)
TILE_SHAPE = (256, 256)
WGS84_CRS = CRS.from_epsg(4326)


def features_for_tile(tile, catalog, scale=1, min_zoom=None, max_zoom=None):
    """Render a tile's source footprints."""
    bounds = Bounds(mercantile.bounds(tile), WGS84_CRS)
    shape = tuple(map(int, Affine.scale(scale) * TILE_SHAPE))
    resolution = get_resolution_in_meters(bounds, shape)

    for idx, source in enumerate(
            catalog.get_sources(
                bounds,
                resolution,
                min_zoom=min_zoom,
                max_zoom=max_zoom,
                include_geometries=True)):
        yield {
            "type": "Feature",
            "geometry": source.geom,
            "properties": {
                "url": source.url,
                "name": source.name,
                "resolution": source.resolution,
                "band": source.band,
                "band_info": source.band_info,
                "meta": source.meta,
                "recipes": source.recipes,
                "priority": source.priority,
                "coverage": source.coverage,
                "acquired_at": source.acquired_at,
                "filename": source.filename,
                "min_zoom": source.min_zoom,
                "max_zoom": source.max_zoom,
            }
        }


def sources_for_tile(tile, catalog, scale=1, min_zoom=None, max_zoom=None):
    """Render a tile's source footprints."""
    bounds = Bounds(mercantile.bounds(tile), WGS84_CRS)
    shape = tuple(map(int, Affine.scale(scale) * TILE_SHAPE))
    resolution = get_resolution_in_meters(bounds, shape)

    for idx, source in enumerate(
            catalog.get_sources(
                bounds, resolution, min_zoom=min_zoom, max_zoom=max_zoom)):
        yield {
            "url": source.url,
            "name": source.name,
            "resolution": source.resolution,
            "band": source.band,
            "band_info": source.band_info,
            "meta": source.meta,
            "recipes": source.recipes,
            "priority": source.priority,
            "coverage": source.coverage,
            "acquired_at": source.acquired_at,
            "filename": source.filename,
            "min_zoom": source.min_zoom,
            "max_zoom": source.max_zoom,
        }
