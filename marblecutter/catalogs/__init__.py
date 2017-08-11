import logging
import os
import urlparse

from marblecutter import get_zoom
from psycopg2.pool import ThreadedConnectionPool
from rasterio import warp
from rasterio.crs import CRS
import requests

Infinity = float("inf")
LOG = logging.getLogger(__name__)
WGS84_CRS = CRS.from_epsg(4326)


class Catalog(object):
    def get_sources(self, (bounds, bounds_crs), resolution):
        raise NotImplemented


class MemoryCatalog(Catalog):
    def __init__(self):
        self._sources = []

    def add_source(self, geometry, attributes):
        self._sources.append((geometry, attributes))

    def get_sources(self, (bounds, bounds_crs), resolution):
        from shapely.geometry import box

        results = []
        zoom = get_zoom(max(resolution))
        ((left, right), (bottom, top)) = warp.transform(
            bounds_crs, WGS84_CRS, bounds[::2], bounds[1::2])
        bounds_geom = box(left, bottom, right, top)
        bounds_centroid = bounds_geom.centroid

        # Filter by zoom level and intersecting geometries
        for candidate in self._sources:
            (geom, attr) = candidate
            if attr['min_zoom'] <= zoom < attr['max_zoom'] and \
               geom.intersects(bounds_geom):
                results.append(candidate)

        # Sort by resolution and centroid distance
        results = sorted(
            results,
            key=lambda (geom, attr): (
                attr['priority'],
                int(attr['resolution']),
                bounds_centroid.distance(geom.centroid),
            )
        )

        # Remove duplicate URLs
        # From https://stackoverflow.com/a/480227
        seen = set()
        seen_add = seen.add
        results = [
            x for x in results
            if not (x[1]['url'] in seen or seen_add(x[1]['url']))
        ]

        # Pick only the attributes we care about
        results = [(a['url'], a['source'], a['resolution'])
                   for (_, a) in results]

        return results


class PostGISCatalog(Catalog):
    def __init__(self, database_url=os.getenv("DATABASE_URL")):
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
                    ST_Centroid(wkb_geometry) <-> ST_Centroid(
                        ST_SetSRID(
                            'BOX(%(minx)s %(miny)s, %(maxx)s %(maxy)s)'::box2d,
                            4326)) distance
                FROM footprints
                WHERE wkb_geometry && ST_SetSRID(
                    'BOX(%(minx)s %(miny)s, %(maxx)s %(maxy)s)'::box2d, 4326)
                    AND %(zoom)s BETWEEN min_zoom AND max_zoom
                    AND enabled = true
                ORDER BY url
            ) AS _
            ORDER BY priority ASC, rounded_resolution ASC, distance ASC
        """

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


from itertools import chain
from shapely.geometry import box


class OAMSceneCatalog(Catalog):
    def __init__(self, uri):
        scene = requests.get(uri).json()

        self._box = box(*scene['bounds'])
        self._bounds = scene['bounds']
        self._center = scene['center']
        self._maxzoom = scene['maxzoom']
        self._minzoom = scene['minzoom']
        self._name = scene['name']

        self._sources = [
            OINMetaCatalog(
                source['meta']['source'].replace('_warped.vrt', '_meta.json'))
            for source in reversed(scene['meta']['sources'])
        ]

    def get_sources(self, (bounds, bounds_crs), resolution):
        return chain(*[
            s.get_sources((bounds, bounds_crs), resolution)
            for s in self._sources
        ])

    @property
    def bounds(self):
        return self._bounds

    @property
    def center(self):
        return self._center

    @property
    def minzoom(self):
        return self._minzoom

    @property
    def maxzoom(self):
        return self._maxzoom


class OINMetaCatalog(Catalog):
    def __init__(self, uri):
        oin_meta = requests.get(uri).json()

        self._box = box(*oin_meta['bbox'])
        self._bounds = oin_meta['bbox']
        self._name = oin_meta['title']
        self._resolution = oin_meta['gsd']
        self._source = oin_meta['uuid']

    def get_sources(self, (bounds, bounds_crs), resolution):
        ((left, right), (bottom, top)) = warp.transform(
            bounds_crs, WGS84_CRS, bounds[::2], bounds[1::2])
        bounds_geom = box(left, bottom, right, top)

        if self._box.intersects(bounds_geom):
            return [(self._source, self._name, self._resolution)]

        return []

    @property
    def bounds(self):
        return self._bounds

    @property
    def minzoom(self):
        # TODO calculate this according to the resolution
        return 0

    @property
    def maxzoom(self):
        # TODO calculate this according to the resolution
        return 22
