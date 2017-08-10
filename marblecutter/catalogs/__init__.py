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


from shapely.geometry import box


class OAMJSONCatalog(Catalog):
    def __init__(self, uri):
        rsp = requests.get(uri)

        """
{
  "name": "Nguna-Taloa",
  "bounds": [
    168.3805985918213,
    -17.48455452893895,
    168.38891800755255,
    -17.48022892413382
  ],
  "minzoom": 9,
  "meta": {
    "footprint": "http://oin-hotosm.s3.amazonaws.com/5796733584ae75bb00ec746a/0/579674e02b67227a79b4fd52_footprint.json",
    "source": "http://oin-hotosm.s3.amazonaws.com/5796733584ae75bb00ec746a/0/579674e02b67227a79b4fd52_warped.vrt",
    "approximateZoom": 22,
    "width": 26399,
    "height": 14038,
    "acquisitionStart": "2015-04-02T07:00:00.000Z",
    "acquisitionEnd": "2015-04-02T07:00:00.000Z",
    "platform": "uav",
    "provider": "Government of Vanuatu",
    "uploadedAt": "2016-07-25T00:00:00.000Z",
    "oinMetadataUrl": "http://oin-hotosm.s3.amazonaws.com/5796733584ae75bb00ec746a/0/579674e02b67227a79b4fd52_meta.json"
  },
  "maxzoom": 25,
  "tilejson": "2.1.0",
  "center": [
    168.38475829968692,
    -17.482391726536385,
    15
  ]
}
        """
        self._meta = rsp.json()
        LOG.info("meta: %s", self._meta)
        self._bbox = box(*self._meta['bounds'])

    def get_sources(self, (bounds, bounds_crs), resolution):
        ((left, right), (bottom, top)) = warp.transform(
            bounds_crs, WGS84_CRS, bounds[::2], bounds[1::2])
        bounds_geom = box(left, bottom, right, top)

        if self._bbox.intersects(bounds_geom):
            return [
                (self._meta['meta']['source'].replace('_warped.vrt', '.tif'),
                 self._meta['name'],
                 0.03325)
            ]

        return []
