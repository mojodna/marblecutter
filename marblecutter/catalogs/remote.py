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
    def __init__(self, endpoint):
        if endpoint is None:
            raise Exception("Endpoint must be provided.")

        self._log = logging.getLogger(__name__)
        self.endpoint = endpoint

    def get_sources(self, bounds, resolution):
        bounds, bounds_crs = bounds
        zoom = get_zoom(max(resolution))

        self._log.info("Resolution: %s; equivalent zoom: %d", resolution, zoom)

        # TODO this isn't round tripping properly
        ((left, right), (bottom, top)) = warp.transform(
            bounds_crs, WGS84_CRS, bounds[::2], bounds[1::2])

        self._log.info("%f %f %f %f", left, bottom, right, top)
        self._log.info("%f %f", *mercantile.lnglat(*bounds[0:2]))
        self._log.info("%f %f", *mercantile.lnglat(*bounds[2:]))

        for tile in mercantile.tiles(left, bottom, right, top, (zoom, )):
            self._log.info("Fetching %d/%d/%d", tile.z, tile.x, tile.y)

            r = requests.get("{}/{}/{}/{}.json".format(self.endpoint, tile.z,
                                                       tile.x, tile.y))

            for source in r.json():
                yield Source(**source)
