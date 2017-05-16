# noqa
# coding=utf-8
from __future__ import division, print_function

import math
import multiprocessing
import re

from affine import Affine
import mercantile
from mercantile import Tile
import numpy as np
import rasterio
from rasterio import transform
from rasterio import warp
from rasterio import windows
from rasterio.crs import CRS
from rasterio.warp import Resampling

from tiler import get_source

HALF_ARC_SEC = (1.0/3600.0)*.5
SKADI_CRS = CRS.from_epsg(4326)
WEB_MERCATOR_CRS = CRS.from_epsg(3857)
SOURCES = (
    "tmp/N38W123.tif",
    "tmp/ned_ca.tif", # EPSG:3310
    "s3://mapzen-dynamic-tiler-test/ned_topobathy/0/ned19_n38x50_w123x25_ca_sanfrancisco_topobathy_2010.tif",
    # "s3://mapzen-dynamic-tiler-test/ned_topobathy/0/ned19_n38x25_w123x00_ca_sanfrancisco_topobathy_2010.tif",
    # "s3://mapzen-dynamic-tiler-test/ned_topobathy/0/ned19_n38x25_w123x25_ca_sanfrancisco_topobathy_2010.tif",
    # "s3://mapzen-dynamic-tiler-test/etopo1/0/ETOPO1_Bed_g_geotiff.tif",
    # "s3://mapzen-dynamic-tiler-test/gmted/0/30N180W_20101117_gmted_mea075.tif",
    # "s3://mapzen-dynamic-tiler-test/srtm/0/N38W123.tif",
    # "s3://mapzen-dynamic-tiler-test/ned13/0/imgn39w123_13.tif",
    # "s3://mapzen-dynamic-tiler-test/ned_topobathy/0/ned19_n38x50_w123x00_ca_sanfrancisco_topobathy_2010.tif",
)
# TARGET_HEIGHT = 3601
# TARGET_WIDTH = 3601
TARGET_HEIGHT = 512
TARGET_WIDTH = 512


def _bbox(x, y):
    return (
        (x - 180) - HALF_ARC_SEC,
        (y - 90) - HALF_ARC_SEC,
        (x - 179) + HALF_ARC_SEC,
        (y - 89) + HALF_ARC_SEC)


SKADI_TILE_NAME_PATTERN = re.compile('^([NS])([0-9]{2})([EW])([0-9]{3})$')
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


def _nodata(dtype):
    if np.issubdtype(dtype, int):
        return np.iinfo(dtype).min
    else:
        return np.finfo(dtype).min


def paste((data_src, src_crs, src_transform), data, bounds, resampling=Resampling.lanczos):
    """ "Reproject" src data into the correct position within a larger image"""

    ((left, right), (bottom, top)) = warp.transform(SKADI_CRS, src_crs, bounds[::2], bounds[1::2])
    bounds = (left, bottom, right, top)
    height, width = data_src.shape[1:]
    transform_dst, _, _ = warp.calculate_default_transform(
        src_crs, src_crs, width, height, *bounds)

    print('paste height: ', height)
    print('paste width: ', width)
    print('paste bounds: ', bounds)

    data_dst = np.empty(
        data.shape,
        dtype=data.dtype,
    )

    nodata = _nodata(data_dst.dtype)

    warp.reproject(
        source=data_src,
        destination=data_dst,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=transform_dst,
        dst_crs=src_crs,
        dst_nodata=nodata,
        resampling=resampling,
        num_threads=multiprocessing.cpu_count(),
    )

    if np.issubdtype(data_dst.dtype, float):
        data_dst = np.ma.masked_values(data_dst, nodata, copy=False)
    else:
        data_dst = np.ma.masked_equal(data_dst, nodata, copy=False)

    # print('pasted mask values: ', np.bincount(data_dst.mask.flatten()))
    # print('pasted fill value: ', data_dst.fill_value)
    # print(data_dst)

    # print('target mask (data): ', data.mask)

    data = np.ma.where(data_dst.mask, data, data_dst)
    data.fill_value = nodata
    # print('target mask values (data): ', np.bincount(data.mask.flatten()))
    # print('target mask values (data_dst): ', np.bincount(data_dst.mask.flatten()))
    # print('target fill value: ', data.fill_value)
    # print(data)

    # # TODO this is totally wrong
    # if data_dst.mask:
    #     data = np.ma.where(data_dst.mask, data, data_dst)
    # else:
    #     data = data_dst
    # data.mask = np.logical_and(data.mask, data_dst.mask)

    return data


def reproject((data_src, src_crs, src_transform), dst_crs, resampling=Resampling.lanczos):
    # calculate a transformation into the dst projection along with
    # resulting dimensions
    height, width = data.shape[1:]
    bounds = transform.array_bounds(height, width, src_transform)
    print('height: ', height)
    print('width: ', width)
    print('bounds: ', bounds)
    transform_dst, width_dst, height_dst = warp.calculate_default_transform(
        src_crs, dst_crs, width, height, *bounds)

    # print('reprojected source fill value: ', data_src.fill_value)
    # print('reprojected source mask values: ', np.bincount(data_src.mask.flatten()))

    data_dst = np.ma.empty(
        (data_src.shape[0], height_dst, width_dst),
        dtype=data_src.dtype,
    )

    nodata = _nodata(data_dst.dtype)

    warp.reproject(
        source=data_src,
        destination=data_dst,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=transform_dst,
        dst_crs=dst_crs,
        dst_nodata=nodata,
        resampling=resampling,
        num_threads=multiprocessing.cpu_count(),
    )

    if np.issubdtype(data_dst.dtype, float):
        data_dst = np.ma.masked_values(data_dst, nodata, copy=False)
    else:
        data_dst = np.ma.masked_equal(data_dst, nodata, copy=False)

    # print('reprojected fill value: ', data_dst.fill_value)
    # print('reprojected mask values: ', np.bincount(data_dst.mask.flatten()))

    return (data_dst, dst_crs, transform_dst)


def read_window(src, bounds):
    ((left, right), (bottom, top)) = warp.transform(SKADI_CRS, src.crs, bounds[::2], bounds[1::2])
    bounds_src = (left, bottom, right, top)
    window = windows.from_bounds(*bounds_src, transform=src.transform, boundless=True)

    # scaling factor
    scale = Affine.scale(max(1, window.num_cols / TARGET_WIDTH),
                         max(1, window.num_rows / TARGET_HEIGHT))

    # crop the data window to available data
    window_src = windows.crop(window, height=src.height, width=src.width)
    window_size = (window_src.num_cols, window_src.num_rows)

    # target shape, scaled
    target_shape = tuple(reversed(map(int, map(math.floor, window_size * ~scale))))

    print('target_shape: ', target_shape)

    # read data
    data = src.read(
        out_shape=(src.count, ) + target_shape,
        window=window_src,
    )

    if src.nodata is not None:
        # some datasets use the min value but report an alternate nodata value
        # mask = np.where((data == src.nodata) | (data == _nodata(data.dtype)), True, False)
        if np.issubdtype(data.dtype, float):
            data = np.ma.masked_values(data, src.nodata, copy=False)
        else:
            data = np.ma.masked_equal(data, src.nodata, copy=False)
    else:
        data = np.ma.masked_array(data, mask=False)

    # print('window mask values: ', np.bincount(data.mask.flatten()))
    # print('window fill value: ', data.fill_value)

    # data = np.ma.asarray(data, dtype=np.float32)
    data = data.astype(np.float32)
    # data.fill_value = _nodata(np.float32)

    # print('window mask values: ', np.bincount(data.mask.flatten()))
    # print('window fill value: ', data.fill_value)

    return (data, src.crs, src.transform * scale)

if __name__ == '__main__':
    # (x, y) = _parse_skadi_tile('N38W123')
    #
    # bounds = _bbox(x, y)
    tile = Tile(324, 787, 11)
    bounds_4326 = mercantile.bounds(tile)

    data = np.ma.empty(
        (1, TARGET_HEIGHT, TARGET_WIDTH),
        dtype=np.float32,
        fill_value=_nodata(np.float32),
    )
    data.mask = True

    for url in SOURCES:
        src = get_source(url)

        print(url)

        # read a window from the source data
        # TODO ask for a buffer here, get back an updated bounding box reflecting it
        window_data = read_window(src, bounds_4326)

        # reproject data into Skadi's CRS
        projected_data = reproject(window_data, WEB_MERCATOR_CRS)

        # paste the resulting data into a common array
        data = paste(projected_data, data, bounds_4326)

    ((left, right), (bottom, top)) = warp.transform(SKADI_CRS, WEB_MERCATOR_CRS, bounds_4326[::2], bounds_4326[1::2])
    bounds_3857 = (left, bottom, right, top)

    profile = src.profile
    profile.update({
        'crs': WEB_MERCATOR_CRS,
        'dtype': data.dtype,
        'transform': transform.from_bounds(*bounds_4326, width=TARGET_WIDTH, height=TARGET_HEIGHT),
        'width': TARGET_WIDTH,
        'height': TARGET_HEIGHT,
        'nodata': data.fill_value,
    })

    with rasterio.open('tmp/3857.tif', 'w', **profile) as out:
        out.write(data.filled())
