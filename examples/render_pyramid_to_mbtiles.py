# noqa
# coding=utf-8
from __future__ import print_function

import argparse
import logging
import os
import random
import time
from functools import wraps
from multiprocessing.dummy import Pool

from shapely import wkb
from shapely.geometry import box

import boto3
import botocore
import mercantile
import psycopg2
import psycopg2.extras
import sqlite3
from marblecutter import tiling
from marblecutter.formats import PNG, GeoTIFF
from marblecutter.sources import MemoryAdapter
from marblecutter.stats import Timer
from marblecutter.transformations import Normal, Terrarium
from mercantile import Tile

logging.basicConfig(level=logging.INFO)
# Quieting boto messages down a little
logging.getLogger('boto3.resources.action').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('marblecutter').setLevel(logging.WARNING)
logging.getLogger('marblecutter.mosaic').setLevel(logging.WARNING)
logging.getLogger('marblecutter.sources').setLevel(logging.WARNING)
logger = logging.getLogger('batchtiler')

if os.environ.get('VERBOSE'):
    logger.setLevel(logging.DEBUG)

POOL_SIZE = 12
POOL = Pool(POOL_SIZE)
MBTILES_POOL = Pool(1)
OVERWRITE = os.environ.get('OVERWRITE_EXISTING_OBJECTS') == 'true'

GEOTIFF_FORMAT = GeoTIFF()
PNG_FORMAT = PNG()
NORMAL_TRANSFORMATION = Normal()
TERRARIUM_TRANSFORMATION = Terrarium()

RENDER_COMBINATIONS = [
    ("normal", NORMAL_TRANSFORMATION, PNG_FORMAT, ".png"),
    ("terrarium", TERRARIUM_TRANSFORMATION, PNG_FORMAT, ".png"),
    ("geotiff", None, GEOTIFF_FORMAT, ".tif"),
]


# From https://www.saltycrane.com/blog/2009/11/trying-out-retry-decorator-python/
def retry(ExceptionToCheck,
          tries=4,
          delay=3,
          backoff=2,
          max_delay=60,
          logger=None):
    def deco_retry(f):
        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except ExceptionToCheck, e:
                    msg = "%s, Retrying in %d seconds..." % (str(e), mdelay)
                    if logger:
                        logger.exception(msg)
                    else:
                        print(msg)
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
                    mdelay = min(mdelay, max_delay)
            return f(*args, **kwargs)

        return f_retry  # true decorator

    return deco_retry


class MbtilesOutput(object):
    def __init__(self, filename, **kwargs):
        self._filename = filename

    def _setup_mbtiles(self, cur):
        cur.execute("""
            CREATE TABLE tiles (
            zoom_level integer,
            tile_column integer,
            tile_row integer,
            tile_data blob);
            """)
        cur.execute("""
            CREATE TABLE metadata
            (name text, value text);
            """)
        cur.execute("""
            CREATE TABLE grids (
            zoom_level integer,
            tile_column integer,
            tile_row integer,
            grid blob);
            """)
        cur.execute("""
            CREATE TABLE grid_data (
            zoom_level integer,
            tile_column integer,
            tile_row integer,
            key_name text,
            key_json text);
            """)
        cur.execute("""
            CREATE UNIQUE INDEX name ON metadata (name);
            """)
        cur.execute("""
            CREATE UNIQUE INDEX tile_index ON tiles (
            zoom_level, tile_column, tile_row);
            """)

    def _optimize_connection(self, cur):
        cur.execute("""
            PRAGMA synchronous=0
            """)
        cur.execute("""
            PRAGMA locking_mode=EXCLUSIVE
            """)
        cur.execute("""
            PRAGMA journal_mode=DELETE
            """)

    def _flip_y(self, zoom, row):
        """
        mbtiles requires WMTS (origin in the upper left),
        and Tilezen stores in TMS (origin in the lower left).
        This adjusts the row/y value to match WMTS.
        """

        if row is None or zoom is None:
            raise TypeError("zoom and row cannot be null")

        return (2 ** zoom) - 1 - row

    def add_metadata(self, name, value):
        self._cur.execute("""
            INSERT INTO metadata (
                name, value
            ) VALUES (
                ?, ?
            );
            """,
            (
                name,
                value,
            )
        )

    def open(self):
        self._conn = sqlite3.connect(self._filename)
        self._cur = self._conn.cursor()
        self._optimize_connection(self._cur)
        self._setup_mbtiles(self._cur)

    def add_tile(self, tile, data):
        self._cur.execute("""
            INSERT INTO tiles (
                zoom_level, tile_column, tile_row, tile_data
            ) VALUES (
                ?, ?, ?, ?
            );
            """,
            (
                tile.z,
                tile.x,
                self._flip_y(tile.z, tile.y),
                sqlite3.Binary(data),
            )
        )

    def close(self):
        self._conn.commit()
        self._conn.close()


def build_source_index(tile, min_zoom, max_zoom):
    source_cache = MemoryAdapter()
    bbox = box(*mercantile.bounds(tile))

    database_url = os.environ.get('DATABASE_URL')

    with psycopg2.connect(database_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT
                    filename, resolution, source, url,
                    min_zoom, max_zoom, priority, approximate_zoom,
                    wkb_geometry
                FROM
                    footprints
                WHERE
                    ST_Intersects(
                        wkb_geometry,
                        ST_GeomFromText(%s, 4326)
                    )
                    AND min_zoom <= %s
                    AND max_zoom >= %s
                    AND enabled = true
                """, (bbox.to_wkt(), min_zoom, max_zoom))

            logger.info("Found %s sources for tile %s, zoom %s-%s",
                cur.rowcount, tile, min_zoom, max_zoom)

            if not cur.rowcount:
                raise ValueError("No sources found for this tile")

            for row in cur:
                row = dict(row)
                shape = wkb.loads(row.pop('wkb_geometry').decode('hex'))
                source_cache.add_source(shape, row)

    return source_cache


def render_tile_exc_wrapper(tile, sources, output):
    try:
        render_tile(tile, sources, output)
    except Exception:
        logger.exception('Error while processing tile %s', tile)
        raise


def render_tile(tile, sources, output):
    for (type, transformation, format, ext) in RENDER_COMBINATIONS:

        with Timer() as t:
            (headers, data) = tiling.render_tile(
                tile, sources, format=format, transformation=transformation)

        logger.debug(
            '(%02d/%06d/%06d) Took %0.3fs to render %s tile (%s bytes), Source: %s, Timers: %s',
            tile.z, tile.x, tile.y, t.elapsed, type,
            len(data),
            headers.get('X-Imagery-Sources'),
            headers.get('X-Timers'),
        )

        MBTILES_POOL.apply_async(
            write_to_mbtiles,
            args=[type, tile, headers, data, output]
        )


def write_to_mbtiles(type, tile, headers, data, output):
    try:
        with Timer() as t:
            outputter = output.get(type)
            outputter.add_tile(tile, data)

        logger.debug(
            '(%02d/%06d/%06d) Took %0.3fs to write %s tile to mbtiles://%s',
            tile.z, tile.x, tile.y, t.elapsed, type,
            outputter._filename,
        )
    except:
        logger.exception("Problem writing to mbtiles")


def queue_tile(tile, max_zoom, sources, output):
    queue_render(tile, sources, output)

    if tile.z < max_zoom:
        for child in mercantile.children(tile):
            queue_tile(child, max_zoom, sources, output)


def queue_render(tile, sources, output):
    logger.debug('Enqueueing render for tile %s', tile)
    POOL.apply_async(render_tile_exc_wrapper, args=[tile, sources, output])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('x', type=int)
    parser.add_argument('y', type=int)
    parser.add_argument('zoom', type=int)
    parser.add_argument('max_zoom', type=int)
    parser.add_argument('mbtiles_prefix')

    args = parser.parse_args()
    root = Tile(args.x, args.y, args.zoom)

    logger.info('Caching sources for root tile %s to zoom %s',
                root, args.max_zoom)

    source_index = build_source_index(root, args.zoom, args.max_zoom)

    output = {}
    for type, _, _, _ in RENDER_COMBINATIONS:
        fname = '{}-{}.mbtiles'.format(args.mbtiles_prefix, type)
        output[type] = MbtilesOutput(fname)
        output[type].open()

    logger.info('Running %s processes', POOL_SIZE)

    queue_tile(root, args.max_zoom, source_index, output)

    POOL.close()
    POOL.join()
    logger.info('Done processing root pyramid %s to zoom %s',
                root, args.max_zoom)

    for outputter in output.values():
        outputter.close()
