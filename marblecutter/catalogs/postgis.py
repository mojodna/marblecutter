# coding=utf-8
from __future__ import absolute_import

import json
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

    def get_sources(self, bounds, resolution, include_geometries=False):
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
            date_range AS (
              SELECT
                COALESCE(min(acquired_at), '1970-01-01') min,
                COALESCE(max(acquired_at), '1970-01-01') max,
                age(COALESCE(max(acquired_at), '1970-01-01'),
                    COALESCE(min(acquired_at), '1970-01-01')) "interval"
              FROM {table}
            ),
            sources AS (
              SELECT * FROM (
                SELECT
                  1 iterations,
                  ARRAY[url] urls,
                  ARRAY[source] sources,
                  ARRAY[resolution] resolutions,
                  ARRAY[coalesce(bands, '{{}}'::jsonb)] bands,
                  ARRAY[coalesce(meta, '{{}}'::jsonb)] metas,
                  ARRAY[coalesce(recipes, '{{}}'::jsonb)] recipes,
                  ARRAY[acquired_at] acquisition_dates,
                  ARRAY[priority] priorities,
                  ARRAY[ST_Area(ST_Intersection(bbox.geom, footprints.geom)) /
                    ST_Area(bbox.geom)] coverages,
                  ARRAY[ST_Multi(footprints.geom)] geometries,
                  ST_Multi(footprints.geom) geom,
                  ST_Difference(bbox.geom, footprints.geom) uncovered
                FROM date_range, {table} footprints
                JOIN bbox ON footprints.geom && bbox.geom
                WHERE %(zoom)s BETWEEN min_zoom and max_zoom
                  AND footprints.enabled = true
                ORDER BY
                  10 * coalesce(footprints.priority, 0.5) *
                    .1 * (1 - (extract(
                      EPOCH FROM (current_timestamp - COALESCE(
                        acquired_at, '2000-01-01'))) /
                        extract(
                          EPOCH FROM (current_timestamp - date_range.min)))) *
                    50 *
                      -- de-prioritize over-zoomed sources
                      CASE WHEN %(resolution)s / footprints.resolution >= 1
                        THEN 1
                        ELSE 1 / footprints.resolution
                      END *
                    ST_Area(
                        ST_Intersection(bbox.geom, footprints.geom)) /
                      ST_Area(bbox.geom) DESC
                LIMIT 1
              ) AS _
              UNION ALL
              SELECT * FROM (
                SELECT
                  sources.iterations + 1,
                  sources.urls || url urls,
                  sources.sources || source sources,
                  sources.resolutions || resolution resolutions,
                  sources.bands || coalesce(
                    footprints.bands, '{{}}'::jsonb) bands,
                  sources.metas || coalesce(meta, '{{}}'::jsonb) metas,
                  sources.recipes || coalesce(
                    footprints.recipes, '{{}}'::jsonb) recipes,
                  sources.acquisition_dates || footprints.acquired_at
                    acquisition_dates,
                  sources.priorities || footprints.priority priorities,
                  sources.coverages || ST_Area(
                    ST_Intersection(sources.uncovered, footprints.geom)) /
                    ST_Area(bbox.geom) coverages,
                  sources.geometries || footprints.geom,
                  ST_Collect(sources.geom, footprints.geom) geom,
                  ST_Difference(sources.uncovered, footprints.geom) uncovered
                FROM bbox, date_range, {table} footprints
                -- use proper intersection to prevent voids from irregular
                -- footprints
                JOIN sources ON ST_Intersects(
                    footprints.geom, sources.uncovered)
                WHERE NOT (footprints.url = ANY(sources.urls))
                  AND %(zoom)s BETWEEN min_zoom AND max_zoom
                  AND footprints.enabled = true
                ORDER BY
                  10 * coalesce(footprints.priority, 0.5) *
                    .1 * (1 - (extract(
                      EPOCH FROM (current_timestamp - COALESCE(
                        acquired_at, '2000-01-01'))) /
                        extract(
                          EPOCH FROM (current_timestamp - date_range.min)))) *
                    50 *
                      -- de-prioritize over-zoomed sources
                      CASE WHEN %(resolution)s / footprints.resolution >= 1
                        THEN 1
                        ELSE 1 / footprints.resolution
                      END *
                    ST_Area(
                        ST_Intersection(sources.uncovered, footprints.geom)) /
                        ST_Area(bbox.geom) DESC
                LIMIT 1
              ) AS _
            ),
            candidates AS (
                SELECT *
                FROM sources
                ORDER BY iterations DESC
                LIMIT 1
            ), candidate_rows AS (
                SELECT
                  unnest(urls) url,
                  unnest(sources) source,
                  unnest(resolutions) resolution,
                  unnest(bands) bands,
                  unnest(metas) meta,
                  unnest(recipes) recipes,
                  unnest(acquisition_dates) acquired_at,
                  unnest(priorities) priority,
                  unnest(coverages) coverage,
                  unnest(geometries) geom
                FROM candidates
            )
            SELECT
              url,
              source,
              resolution,
              bands,
              meta,
              recipes,
              acquired_at,
              null band,
              priority,
              coverage,
              CASE WHEN {include_geometries}
                  THEN ST_AsGeoJSON(geom)
                  ELSE 'null'
              END geom
            FROM candidate_rows
        """.format(
            table=self.table,
            geometry_column=self.geometry_column,
            include_geometries=bool(include_geometries))

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
                    "resolution": min(resolution),
                })

                for record in cur:
                    yield Source(*record[:-1], geom=json.loads(record[-1]))
        except Exception as e:
            self._log.error(e)
        finally:
            self._pool.putconn(conn)
