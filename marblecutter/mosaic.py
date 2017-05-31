# noqa
# coding=utf-8
from __future__ import absolute_import, division, print_function

import logging
import multiprocessing
import os
import urlparse

from affine import Affine
import numpy as np
from psycopg2.pool import SimpleConnectionPool
from rasterio import transform
from rasterio import warp
from rasterio.warp import Resampling

urlparse.uses_netloc.append('postgis')
urlparse.uses_netloc.append('postgres')
database_url = urlparse.urlparse(os.environ['DATABASE_URL'])
pool = SimpleConnectionPool(
    1,
    16,
    database=database_url.path[1:],
    user=database_url.username,
    password=database_url.password,
    host=database_url.hostname,
    port=database_url.port,
)

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
                "minx": left,
                "miny": bottom,
                "maxx": right,
                "maxy": top,
                "zoom": zoom,
            })

            return cur.fetchall()
    finally:
        pool.putconn(conn)


def paste((src_data, (src_bounds, src_crs)), (canvas, (canvas_bounds, canvas_bounds_crs)), resampling=Resampling.lanczos):
    """ "Reproject" src data into the correct position within a larger image"""
    from . import _mask, _nodata

    src_height, src_width = src_data.shape[1:]
    canvas_height, canvas_width = canvas.shape[1:]

    src_transform = transform.from_bounds(*src_bounds, width=src_width, height=src_height)
    canvas_transform = transform.from_bounds(*canvas_bounds, width=canvas_width, height=canvas_height)

    dst_data = np.empty(
        canvas.shape,
        dtype=canvas.dtype,
    )

    nodata = _nodata(dst_data.dtype)

    warp.reproject(
        source=src_data,
        destination=dst_data,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=canvas_transform,
        dst_crs=canvas_bounds_crs,
        dst_nodata=nodata,
        resampling=resampling,
        num_threads=multiprocessing.cpu_count(),
    )

    dst_data = _mask(dst_data, nodata)

    canvas = np.ma.where(canvas.mask & ~dst_data.mask, dst_data, canvas)

    canvas.fill_value = nodata

    return canvas
