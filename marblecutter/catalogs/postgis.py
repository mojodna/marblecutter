# coding=utf-8
from __future__ import absolute_import

import logging
import os
import urlparse

from rasterio import warp

from marblecutter import get_zoom
from psycopg2.pool import ThreadedConnectionPool

from . import WGS84_CRS, Catalog

Infinity = float("inf")


class PostGISCatalog(Catalog):
    def __init__(self, table="footprints", database_url=os.getenv("DATABASE_URL"), geometry_column="wkb_geometry"):
        if database_url is None:
            raise Exception(
                "Database URL must be provided, either as an arg or as DATABASE_URL."
            )
        urlparse.uses_netloc.append('postgis')
        urlparse.uses_netloc.append('postgres')
        url = urlparse.urlparse(database_url)

        self._pool = ThreadedConnectionPool(
            1,
            16,
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port, )

        self._log = logging.getLogger(__name__)
        self.table = table
        self.geometry_column = geometry_column

    def get_sources(self, (bounds, bounds_crs), resolution):
        zoom = get_zoom(max(resolution))

        self._log.info("Resolution: %s; equivalent zoom: %d", resolution, zoom)

        # TODO get sources in native CRS of the target
        query = """
            SELECT
                url,
                source,
                resolution
            FROM (
                SELECT
                    DISTINCT ON (url) url,
                    source,
                    resolution,
                    priority,
                    -- group sources by approximate resolution
                    round(resolution) rounded_resolution,
                    -- measure the distance from centroids to prioritize overlap
                    ST_Centroid({geometry_column}) <-> ST_Centroid(
                        ST_SetSRID(
                            'BOX(%(minx)s %(miny)s, %(maxx)s %(maxy)s)'::box2d,
                            4326)) distance
                FROM {table}
                WHERE {geometry_column} && ST_SetSRID(
                    'BOX(%(minx)s %(miny)s, %(maxx)s %(maxy)s)'::box2d, 4326)
                    AND %(zoom)s BETWEEN min_zoom AND max_zoom
                    AND enabled = true
                ORDER BY url
            ) AS _
            ORDER BY priority ASC, rounded_resolution ASC, distance ASC
        """.format(table=self.table, geometry_column=self.geometry_column)

        # height and width of the CRS
        ((left, right), (bottom, top)) = warp.transform(
            bounds_crs, WGS84_CRS, bounds[::2], bounds[1::2])

        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(query, {
                    "minx": left if left != Infinity else -180,
                    "miny": bottom if bottom != Infinity else -90,
                    "maxx": right if right != Infinity else 180,
                    "maxy": top if top != Infinity else 90,
                    "zoom": zoom,
                })

                return cur.fetchall()
        finally:
            self._pool.putconn(conn)
