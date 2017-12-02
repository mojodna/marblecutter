# coding=utf-8
from __future__ import absolute_import

import logging
import os

from marblecutter import get_zoom
from psycopg2.pool import ThreadedConnectionPool
from rasterio import warp

from . import WGS84_CRS, Catalog
from ..utils import Source

try:
    import urllib.parse as urlparse
except ImportError:
    import urlparse


Infinity = float("inf")


class PostGISCatalog(Catalog):
    def __init__(self,
                 table="footprints",
                 database_url=os.getenv("DATABASE_URL"),
                 geometry_column="geom"):
        if database_url is None:
            raise Exception("Database URL must be provided.")
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
            port=url.port)

        self._log = logging.getLogger(__name__)
        self.table = table
        self.geometry_column = geometry_column

    def get_sources(self, bounds, resolution):
        bounds, bounds_crs = bounds
        zoom = get_zoom(max(resolution))

        self._log.info("Resolution: %s; equivalent zoom: %d", resolution, zoom)

        # TODO get sources in native CRS of the target
        query = """
            WITH RECURSIVE bbox AS (
              SELECT ST_SetSRID(
                    'BOX(%(minx)s %(miny)s, %(maxx)s %(maxy)s)'::box2d,
                    4326) geom
            ),
            sources AS (
              SELECT * FROM (
                SELECT
                  1 iterations,
                  ARRAY[url] urls,
                  ARRAY[source] sources,
                  ARRAY[resolution] resolutions,
                  ARRAY[bands] bands,
                  ARRAY[meta] metas,
                  ARRAY[recipes] recipes,
                  ST_Multi(footprints.geom) geom,
                  ST_Difference(bbox.geom, footprints.geom) uncovered
                FROM {table} footprints
                JOIN bbox ON footprints.geom && bbox.geom
                WHERE %(zoom)s BETWEEN min_zoom and max_zoom
                  AND footprints.enabled = true
                ORDER BY
                  footprints.priority ASC,
                  round(footprints.resolution) ASC,
                  ST_Centroid(footprints.geom) <-> ST_Centroid(bbox.geom),
                  footprints.url DESC
                LIMIT 1
              ) AS _
              UNION ALL
              SELECT * FROM (
                SELECT
                  sources.iterations + 1,
                  sources.urls || url urls,
                  sources.sources || source sources,
                  sources.resolutions || resolution resolutions,
                  sources.bands || footprints.bands,
                  sources.metas || meta metas,
                  sources.recipes || footprints.recipes,
                  ST_Collect(sources.geom, footprints.geom) geom,
                  ST_Difference(sources.uncovered, footprints.geom) uncovered
                FROM {table} footprints
                -- use proper intersection to prevent voids from irregular
                -- footprints
                JOIN sources ON ST_Intersects(
                    footprints.geom, sources.uncovered)
                WHERE NOT (footprints.url = ANY(sources.urls))
                  AND %(zoom)s BETWEEN min_zoom AND max_zoom
                  AND footprints.enabled = true
                ORDER BY
                  footprints.priority ASC,
                  round(footprints.resolution) ASC,
                  -- prefer sources that reduce uncovered area the most
                  ST_Area(
                    ST_Difference(sources.uncovered, footprints.geom)) ASC,
                  -- if multiple scenes exist, assume they include timestamps
                  footprints.url DESC
                LIMIT 1
              ) AS _
            ),
            candidates AS (
                SELECT *
                FROM sources
                ORDER BY iterations DESC
                LIMIT 1
            )
            SELECT
              unnest(urls) url,
              unnest(sources) source,
              unnest(resolutions) resolution,
              unnest(bands) bands,
              unnest(metas) meta,
              unnest(recipes) recipes
            FROM candidates
        """.format(
            table=self.table, geometry_column=self.geometry_column)

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

                for record in cur:
                    yield Source(*record)
        finally:
            self._pool.putconn(conn)
