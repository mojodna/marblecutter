# coding=utf-8
from __future__ import absolute_import

import numpy as np

from rasterio import warp
from rasterio.crs import CRS

from .. import Bounds, PixelCollection, crop, get_extent, get_resolution

WGS84_CRS = CRS.from_epsg(4326)


class TransformationBase:
    buffer = 0

    def __init__(self, collar=0):
        self.collar = collar

    def expand(self, bounds, shape):
        buffer = self.buffer
        collar = self.collar
        effective_buffer = buffer + collar

        if effective_buffer == 0:
            return bounds, shape, (0, 0, 0, 0)

        resolution = get_resolution(bounds, shape)

        # apply buffer
        bounds_orig = bounds
        shape = [dim + (2 * effective_buffer) for dim in shape]
        bounds = Bounds([
            p - (buffer * resolution[i % 2])
            if i < 2 else p + (effective_buffer * resolution[i % 2])
            for i, p in enumerate(bounds.bounds)
        ], bounds.crs)

        #
        left = right = bottom = top = buffer

        # adjust bounds + shape if bounds extends outside the extent
        extent = get_extent(bounds.crs)

        # TODO this is all or nothing right now rather than clipping to the
        # extent
        # also: float precision
        if bounds.bounds[0] < extent[0]:
            shape[1] -= effective_buffer
            bounds.bounds[0] = bounds_orig.bounds[0]
            left = 0

        if bounds.bounds[2] > extent[2]:
            shape[1] -= effective_buffer
            bounds.bounds[2] = bounds_orig.bounds[2]
            right = 0

        if bounds.bounds[1] < extent[1]:
            shape[0] -= effective_buffer
            bounds.bounds[1] = bounds_orig.bounds[1]
            bottom = 0

        if bounds.bounds[3] > extent[3]:
            shape[0] -= effective_buffer
            bounds.bounds[3] = bounds_orig.bounds[3]
            top = 0

        return bounds, tuple(shape), (left, bottom, right, top)

    def postprocess(self, pixels, data_format, offsets):
        data, (bounds, data_crs), _ = pixels
        data, (cropped_bounds, data_crs), _ = crop(pixels, data_format,
                                                   offsets)

        if self.collar > 0:
            extent = get_extent(data_crs)

            if data_format == "RGBA":
                if np.isclose(bounds[0], extent[0]):
                    # wrap left
                    cols = data[:, :self.collar]
                    data = np.hstack((cols, data))

                if np.isclose(bounds[2], extent[2]):
                    # wrap right
                    cols = data[:, -self.collar:]
                    data = np.hstack((data, cols))

                if np.isclose(bounds[1], extent[1]):
                    # repeat bottom
                    rows = data[-self.collar:]
                    data = np.vstack((data, rows))

                if np.isclose(bounds[3], extent[3]):
                    # repeat top
                    rows = data[:self.collar]
                    data = np.vstack((rows, data))
            else:
                raise Exception(
                    "Unsupported format for collar postprocessing: {}".format(
                        data_format))

        return PixelCollection(data, Bounds(cropped_bounds, data_crs))

    def transform(self, pixels):
        return pixels, "raw"


def apply_latitude_adjustments(pixels):
    data, (bounds, crs), _ = pixels
    (_, height, width) = data.shape

    ys = np.interp(np.arange(height), [0, height - 1], [bounds[3], bounds[1]])
    xs = np.empty_like(ys)
    xs.fill(bounds[0])

    longitudes, latitudes = warp.transform(crs, WGS84_CRS, xs, ys)

    factors = 1 / np.cos(np.radians(latitudes))

    # convert to 2d array, rotate 270º, scale data
    return PixelCollection(data * np.rot90(np.atleast_2d(factors), 3),
                           pixels.bounds)
