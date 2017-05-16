# noqa
import logging

from affine import Affine
from mercantile import Tile
from rasterio import windows

from tiler import make_window, make_window_from_tile


LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

TRANSFORM = Affine(611.4962261962891, 0.0, -20037508.34,
                   0.0, -611.4962261962891, 20037508.34)
CRS = {'init': 'EPSG:3857'}

def test_global_make_window():
    tile = Tile(0, 0, 0)
    (window, buffers, scale) = make_window(18, tile)

    assert [[0, 67108864], [0, 67108864]] == window
    assert (0, 0, 0, 0) == buffers
    assert 262144 == scale


def test_global_make_window_with_buffer():
    tile = Tile(0, 0, 0)
    (window, buffers, scale) = make_window(18, tile, buffer=2)

    assert [[0, 67108864], [0, 67108864]] == window
    assert (0, 0, 0, 0) == buffers
    assert 262144 == scale


def test_make_window():
    tile = Tile(654, 1583, 12)
    (window, buffers, scale) = make_window(18, tile)

    assert [[25935872, 25952256], [10715136, 10731520]] == window
    assert (0, 0, 0, 0) == buffers
    assert 2**6 == scale


def test_make_window_with_buffer():
    tile = Tile(654, 1583, 12)
    (window, buffers, scale) = make_window(18, tile, buffer=2)

    assert [[25935744, 25952384], [10715008, 10731648]] == window
    assert (2, 2, 2, 2) == buffers
    assert 2**6 == scale


def test_make_window_corner():
    tile = Tile(0, 0, 12)
    (window, buffers, scale) = make_window(18, tile)

    assert [[0, 16384], [0, 16384]] == window
    assert (0, 0, 0, 0) == buffers
    assert 2**6 == scale


def test_make_window_corner_with_buffer():
    tile = Tile(0, 0, 12)
    (window, buffers, scale) = make_window(18, tile, buffer=2)

    assert [[0, 16512], [0, 16512]] == window
    assert (0, 2, 2, 0) == buffers
    assert 2**6 == scale


def test_make_window_left():
    tile = Tile(0, 1583, 12)
    (window, buffers, scale) = make_window(18, tile)

    assert [[25935872, 25952256], [0, 16384]] == window
    assert (0, 0, 0, 0) == buffers
    assert 2**6 == scale


def test_make_window_left_with_buffer():
    tile = Tile(0, 1583, 12)
    (window, buffers, scale) = make_window(18, tile, buffer=2)

    assert [[25935744, 25952384], [0, 16512]] == window
    assert (0, 2, 2, 2) == buffers
    assert 2**6 == scale


def test_make_window_top():
    tile = Tile(654, 0, 12)
    (window, buffers, scale) = make_window(18, tile)

    assert [[0, 16384], [10715136, 10731520]] == window
    assert (0, 0, 0, 0) == buffers
    assert 2**6 == scale


def test_make_window_top_with_buffer():
    tile = Tile(654, 0, 12)
    (window, buffers, scale) = make_window(18, tile, buffer=2)

    assert [[0, 16512], [10715008, 10731648]] == window
    assert (2, 2, 2, 0) == buffers
    assert 2**6 == scale


def test_make_window_from_tile():
    tile = Tile(10, 22, 6)

    (window, buffers, scale) = make_window_from_tile(tile, CRS, TRANSFORM)

    assert windows.Window.from_ranges((22528, 23552), (10240, 11264)) == window
    assert (0, 0, 0, 0) == buffers
    assert 4.0 == scale


def test_buffered_make_window_from_tile():
    tile = Tile(10, 22, 6)

    (window, buffers, scale) = make_window_from_tile(tile, CRS, TRANSFORM, buffer=2)

    assert windows.Window.from_ranges((22520, 23560), (10232, 11272)) == window
    assert (2, 2, 2, 2) == buffers
    assert 4.0 == scale


# def test_buffered_make_window_from_tile_at_corner():
#     tile = Tile(0, 0, 6)
#
#     (window, buffers, scale) = make_window_from_tile(tile, CRS, TRANSFORM, buffer=2)
#
#     assert windows.Window.from_ranges((0, 1032), (0, 1032)) == window
#     assert (0, 2, 2, 0) == buffers
#     assert 4.0 == scale
#
#
# def test_buffered_make_window_from_tile_on_left():
#     tile = Tile(0, 22, 6)
#
#     (window, buffers, scale) = make_window_from_tile(tile, CRS, TRANSFORM, buffer=2)
#
#     assert windows.Window.from_ranges((22520, 23560), (0, 1032)) == window
#     assert (0, 2, 2, 2) == buffers
#     assert 4.0 == scale
#
#
# def test_buffered_make_window_from_tile_on_right():
#     tile = Tile(63, 22, 6)
#
#     (window, buffers, scale) = make_window_from_tile(tile, CRS, TRANSFORM, buffer=2)
#
#     assert windows.Window.from_ranges((22520, 23560), (64504, 65536)) == window
#     assert (2, 2, 0, 2) == buffers
#     assert 4.0 == scale
#
#
# def test_buffered_make_window_from_tile_on_bottom():
#     tile = Tile(10, 63, 6)
#
#     (window, buffers, scale) = make_window_from_tile(tile, CRS, TRANSFORM, buffer=2)
#
#     assert windows.Window.from_ranges((64504, 65536), (10232, 11272)) == window
#     assert (2, 0, 2, 2) == buffers
#     assert 4.0 == scale
#
#
# def test_make_window_from_tile_on_bottom():
#     tile = Tile(10, 63, 6)
#
#     (window, buffers, scale) = make_window_from_tile(tile, CRS, TRANSFORM)
#
#     assert windows.Window.from_ranges((64512, 65536), (10240, 11264)) == window
#     assert (0, 0, 0, 0) == buffers
#     assert 4.0 == scale
