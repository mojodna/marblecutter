# noqa
# coding=utf-8
from __future__ import print_function

import logging

from marblecutter import tiling
from marblecutter.catalogs import PostGISCatalog
from marblecutter.formats import PNG
from marblecutter.transformations import Normal
from mercantile import Tile

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    zoom = 2

    tile = Tile(0, 0, zoom)
    (headers, data) = tiling.render_tile(
        tile,
        PostGISCatalog(),
        format=PNG(),
        transformation=Normal(collar=2),
        scale=2)

    print("Headers: ", headers)

    with open("tmp/{}_{}_{}_buffered_normal.png".format(
            tile.z, tile.x, tile.y), "w") as f:
        f.write(data)

    tile = Tile(0, 2**zoom - 1, zoom)
    (headers, data) = tiling.render_tile(
        tile,
        PostGISCatalog(),
        format=PNG(),
        transformation=Normal(collar=2),
        scale=2)

    print("Headers: ", headers)

    with open("tmp/{}_{}_{}_buffered_normal.png".format(
            tile.z, tile.x, tile.y), "w") as f:
        f.write(data)

    tile = Tile(2**2 - 1, 2**zoom - 1, zoom)
    (headers, data) = tiling.render_tile(
        tile,
        PostGISCatalog(),
        format=PNG(),
        transformation=Normal(collar=2),
        scale=2)

    print("Headers: ", headers)

    with open("tmp/{}_{}_{}_buffered_normal.png".format(
            tile.z, tile.x, tile.y), "w") as f:
        f.write(data)

    tile = Tile(2**zoom - 1, 0, zoom)
    (headers, data) = tiling.render_tile(
        tile,
        PostGISCatalog(),
        format=PNG(),
        transformation=Normal(collar=2),
        scale=2)

    print("Headers: ", headers)

    with open("tmp/{}_{}_{}_buffered_normal.png".format(
            tile.z, tile.x, tile.y), "w") as f:
        f.write(data)
