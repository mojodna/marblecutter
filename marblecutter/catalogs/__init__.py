# coding=utf-8
from __future__ import absolute_import

import mercantile
from rasterio.crs import CRS

from .. import InvalidTileRequest

WGS84_CRS = CRS.from_epsg(4326)


class Catalog(object):
    _bounds = [-180, -85.05113, 180, 85.05113]
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
        return self._bounds

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
        raise NotImplemented

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
