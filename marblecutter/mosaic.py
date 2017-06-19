# noqa
# coding=utf-8
from __future__ import absolute_import, division, print_function

import logging
import os
import urlparse

import numpy as np
from rasterio import warp
from rasterio.crs import CRS

from psycopg2.pool import ThreadedConnectionPool

urlparse.uses_netloc.append('postgis')
urlparse.uses_netloc.append('postgres')
database_url = urlparse.urlparse(os.environ['DATABASE_URL'])
pool = ThreadedConnectionPool(
    1,
    16,
    database=database_url.path[1:],
    user=database_url.username,
    password=database_url.password,
    host=database_url.hostname,
    port=database_url.port,
)

Infinity = float("inf")
LOG = logging.getLogger(__name__)
WGS84_CRS = CRS.from_epsg(4326)


def composite(sources, (bounds, bounds_crs), (height, width), target_crs):
    """Composite data from sources into a single raster covering bounds, but in
    the target CRS."""
    from . import _nodata, get_source, read_window

    canvas = np.ma.empty(
        (1, height, width),
        dtype=np.float32,
        fill_value=_nodata(np.float32),
    )
    canvas.mask = True
    canvas.fill_value = _nodata(np.float32)

    ((left, right), (bottom, top)) = warp.transform(
        bounds_crs, target_crs, bounds[::2], bounds[1::2])
    canvas_bounds = (left, bottom, right, top)

    # iterate over available sources, sorted by decreasing resolution
    for (url, source_name, resolution) in sources:
        src = get_source(url)

        LOG.info("Compositing %s (%s)...", url, source_name)

        # read a window from the source data
        # TODO ask for a buffer here, get back an updated bounding box
        # reflecting it
        # TODO NamedTuple for bounds (bounds + CRS)
        window_data = read_window(
            src, (canvas_bounds, target_crs), (height, width))

        if not window_data:
            continue

        # paste (and reproject) the resulting data onto a canvas
        # TODO NamedTuple for data (data + bounds)
        canvas = paste(window_data, (canvas, (canvas_bounds, target_crs)))

        # TODO get the sub-array that contains nodata pixels and only fetch
        # sources that could potentially fill those (see
        # windows.get_data_window for the inverse)
        if not canvas.mask.any():
            # stop if all pixels are valid
            break

    return (canvas, (canvas_bounds, target_crs))


def get_sources((bounds, bounds_crs), resolution):
    """
    Fetch sources intersecting a bounding box, curated for a specific
    resolution (in terms of zoom).

    Returns a tuple of (url, source name, resolution).
    """
    from . import get_zoom

    zoom = get_zoom(max(resolution))

    LOG.info("Resolution: %s; equivalent zoom: %d", resolution, zoom)

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

    conn = pool.getconn()
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
        pool.putconn(conn)


def paste(
    (window_data, (window_bounds, window_crs)),
    (canvas, (canvas_bounds, canvas_crs))
):
    """ "Reproject" src data into the correct position within a larger image"""
    if window_crs != canvas_crs:
        raise Exception(
            "CRSes must match: {} != {}".format(window_crs, canvas_crs))

    if window_bounds != canvas_bounds:
        raise Exception(
            "Bounds must match: {} != {}".format(window_bounds, canvas_bounds))

    if window_data.shape != canvas.shape:
        raise Exception(
            "Data shapes must match: {} != {}".format(
                window_data.shape, canvas.shape))

    return np.ma.where(canvas.mask & ~window_data.mask, window_data, canvas)
