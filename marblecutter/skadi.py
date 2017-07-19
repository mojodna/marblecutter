# noqa
# coding=utf-8
from __future__ import absolute_import, division

import re

from rasterio.crs import CRS

from . import render
from .formats import Skadi

HALF_ARC_SEC = (1 / 3600) * .5
SHAPE = (3601, 3601)
SKADI_CRS = CRS.from_epsg(4326)
SKADI_FORMAT = Skadi()
SKADI_TILE_NAME_PATTERN = re.compile('^([NS])([0-9]{2})([EW])([0-9]{3})$')


def _bbox(x, y):
    return ((x - 180) - HALF_ARC_SEC, (y - 90) - HALF_ARC_SEC,
            (x - 179) + HALF_ARC_SEC, (y - 89) + HALF_ARC_SEC)


def _parse_skadi_tile(tile_name):
    m = SKADI_TILE_NAME_PATTERN.match(tile_name)
    if m:
        y = int(m.group(2))
        x = int(m.group(4))
        if m.group(1) == 'S':
            y = -y
        if m.group(3) == 'W':
            x = -x
        return (x + 180, y + 90)
    return None


def render_tile(tile, source_provider):
    """Render a tile into gzipped HGT."""
    bounds = _bbox(*_parse_skadi_tile(tile))

    return render(
        (bounds, SKADI_CRS),
        source_provider,
        SHAPE,
        SKADI_CRS,
        format=SKADI_FORMAT)
