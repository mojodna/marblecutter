from marblecutter import get_zoom
from psycopg2.pool import ThreadedConnectionPool
from rasterio import warp
from rasterio.crs import CRS
from shapely.geometry import box


Infinity = float("inf")
WGS84_CRS = CRS.from_epsg(4326)


class SourceAdapter(object):
    def get_sources(self, (bounds, bounds_crs), resolution):
        raise NotImplemented


class MemoryAdapter(SourceAdapter):
    def __init__(self):
        self._sources = []

    def add_source(self, geometry, attributes):
        self._sources.append((geometry, attributes))

    def get_sources(self, (bounds, bounds_crs), resolution):
        results = []
        zoom = get_zoom(max(resolution))
        ((left, right), (bottom, top)) = warp.transform(
            bounds_crs, WGS84_CRS, bounds[::2], bounds[1::2])
        bounds_geom = box(left, right, bottom, top)

        for candidate in self._sources:
            (geom, attr) = candidate
            if attr['min_zoom'] <= zoom < attr['max_zoom'] and \
               geom.intersects(bounds_geom):
                results.append(
                    (attr['url'], attr['source'], attr['resolution'])
                )

        return sorted(results, key=lambda r: r[2])


class PostGISAdapter(SourceAdapter):
    def __init__(self, database_url):
        self._pool = ThreadedConnectionPool(
            1,
            16,
            database_url,
        )

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
