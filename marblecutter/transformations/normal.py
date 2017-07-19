# noqa
# coding=utf-8
from __future__ import absolute_import, division, print_function

import bisect

import numpy as np

from .. import get_resolution_in_meters
from .utils import TransformationBase, apply_latitude_adjustments


# Generate a table of heights suitable for use as hypsometric tinting. These
# have only a little precision for bathymetry, and concentrate most of the
# rest in the 0-3000m range, which is where most of the world's population
# lives.
#
# It seemed better to have this as a function which returned the table rather
# than include the table verbatim, as this would be a big blob of unreadable
# numbers.
def _generate_mapping_table():
    table = []
    for i in range(0, 11):
        table.append(-11000 + i * 1000)
    table.append(-100)
    table.append(-50)
    table.append(-20)
    table.append(-10)
    table.append(-1)
    for i in range(0, 150):
        table.append(20 * i)
    for i in range(0, 60):
        table.append(3000 + 50 * i)
    for i in range(0, 29):
        table.append(6000 + 100 * i)
    return table


# Make a constant version of the table for reference.
HEIGHT_TABLE = _generate_mapping_table()


# Function which returns the index of the maximum height in the height table
# which is lower than the input `h`. I.e: it rounds down. We then _flip_ the
# table "backwards" so that low heights have higher indices. This is so that
# when it's displayed on a regular computer, the lower values near sea level
# have high alpha, making them more opaque.
def _height_mapping_func(h):
    return 255 - bisect.bisect_left(HEIGHT_TABLE, h)


class Normal(TransformationBase):
    buffer = 4

    def transform(self, (data, (bounds, crs))):
        (count, height, width) = data.shape

        if count != 1:
            raise Exception("Can't produce normals from multiple bands")

        (dx, dy) = get_resolution_in_meters((bounds, crs), (height, width))
        data = apply_latitude_adjustments(data, (bounds, crs))[0]

        ygrad, xgrad = np.gradient(data, 2)
        img = np.dstack((-1.0 / dx * xgrad, 1.0 / dy * ygrad,
                         np.ones(data.shape)))

        # first, we normalise to unit vectors. this puts each element of img
        # in the range (-1, 1). the "einsum" stuff is serious black magic, but
        # what it (should be) saying is "for each i,j in the rows and columns,
        # the output is the sum of img[i,j,k]*img[i,j,k]" - i.e: the square.
        norm = np.sqrt(np.einsum('ijk,ijk->ij', img, img))

        # the norm is now the "wrong shape" according to numpy, so we need to
        # copy the norm value out into RGB components.
        norm_copy = norm[:, :, np.newaxis]

        # dividing the img by norm_copy should give us RGB components with
        # values between -1 and 1, but we need values between 0 and 255 for
        # PNG channels. so we move and scale the values to fit in that range.
        scaled = (128.0 * (img / norm_copy + 1.0))

        # and finally clip it to (0, 255) just in case
        img = np.clip(scaled, 0.0, 255.0).astype(np.uint8)

        # apply the height mapping function to get the table index.
        func = np.vectorize(_height_mapping_func)
        hyps = func(data).astype(np.uint8)

        # turn masked values transparent
        if data.mask.any():
            hyps[data.mask] = 0

        # Create output as a 4-channel RGBA image, each (byte) channel
        # corresponds to x, y, z, h where x, y and z are the respective
        # components of the normal, and h is an index into a hypsometric tint
        # table (see HEIGHT_TABLE).
        return (np.dstack((img, hyps)), "RGBA")
