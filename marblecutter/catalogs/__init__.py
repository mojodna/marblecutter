# coding=utf-8
from __future__ import absolute_import

import mercantile
from rasterio.crs import CRS

from .. import InvalidTileRequest

MIN_LAT = -85.05113
MIN_LON = -180.0
MAX_LAT = 85.05113
MAX_LON = 180
WGS84_CRS = CRS.from_epsg(4326)


class Catalog(object):
    _bounds = [MIN_LON, MIN_LAT, MAX_LON, MAX_LAT]
    _center = [0, 0, 2]
    _headers = {}
    _id = None
    _maxzoom = 22
    _metadata_url = None
    _minzoom = 0
    _name = "Untitled"
    _provider = None
    _provider_url = None

    @property
    def bounds(self):
        w, s, e, n = self._bounds
        return (max(MIN_LON, w), max(MIN_LAT, s), min(MAX_LON, e), min(MAX_LAT, n))

    @property
    def center(self):
        return self._center

    @property
    def headers(self):
        return self._headers

    @property
    def id(self):
        return self._id

    @property
    def maxzoom(self):
        return self._maxzoom

    @property
    def metadata_url(self):
        return self._metadata_url

    @property
    def minzoom(self):
        return self._minzoom

    @property
    def name(self):
        return self._name

    @property
    def provider(self):
        return self._provider

    @property
    def provider_url(self):
        return self._provider_url

    def get_sources(self, bounds, resolution):
        raise NotImplementedError

    def validate(self, tile):
        if not self.minzoom <= tile.z <= self.maxzoom:
            raise InvalidTileRequest(
                "Invalid zoom: {} outside [{}, {}]".format(
                    tile.z, self.minzoom, self.maxzoom
                )
            )

        sw = mercantile.tile(*self.bounds[0:2], zoom=tile.z)
        ne = mercantile.tile(*self.bounds[2:4], zoom=tile.z)

        if not sw.x <= tile.x <= ne.x:
            raise InvalidTileRequest(
                "Invalid x coordinate: {} outside [{}, {}]".format(tile.x, sw.x, ne.x)
            )

        if not ne.y <= tile.y <= sw.y:
            raise InvalidTileRequest(
                "Invalid y coordinate: {} outside [{}, {}]".format(tile.y, sw.y, ne.y)
            )
