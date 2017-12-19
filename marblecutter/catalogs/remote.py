# coding=utf-8
from __future__ import absolute_import

import logging

import requests

import mercantile
from marblecutter import get_zoom
from rasterio import warp

from . import WGS84_CRS, Catalog
from ..utils import Source

Infinity = float("inf")


class RemoteCatalog(Catalog):
    def __init__(self, tilejson_url, endpoint):
        if tilejson_url is None:
            raise Exception("Endpoint must be provided.")

        self._log = logging.getLogger(__name__)
        self.endpoint = endpoint

        meta = requests.get(tilejson_url).json()
        self._bounds = meta["bounds"]
        self._center = meta["center"]
        self._maxzoom = meta["maxzoom"]
        self._minzoom = meta["minzoom"]
        self._name = meta["name"]

    def get_sources(self, bounds, resolution):
        bounds, bounds_crs = bounds
        zoom = get_zoom(max(resolution))

        self._log.info("Resolution: %s; equivalent zoom: %d", resolution, zoom)

        left, bottom, right, top = warp.transform_bounds(
            bounds_crs, WGS84_CRS, *bounds)

        # account for rounding errors when converting between tiles and coords
        left += 0.000001
        bottom += 0.000001
        right -= 0.000001
        top -= 0.000001

        if (self._bounds[0] <= left <= self._bounds[2]
                or self._bounds[0] <= right <= self._bounds[2]) and (
                    self._bounds[1] <= bottom <= self._bounds[3]
                    or self._bounds[1] <= top <= self._bounds[3]) and (
                        self._minzoom <= zoom <= self._maxzoom):
            tile = mercantile.bounding_tile(left, bottom, right, top)

            with requests.get(
                    self.endpoint.format(x=tile.x, y=tile.y, z=tile.z)) as rsp:
                if not rsp:
                    self._log.warn("%s failed: %s", rsp.url, rsp.text)
                    return

                for source in rsp.json():
                    yield Source(**source)
