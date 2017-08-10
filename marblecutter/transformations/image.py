# noqa
# coding=utf-8
from __future__ import absolute_import, division, print_function

import numpy as np

from .utils import TransformationBase


class Image(TransformationBase):
    def transform(self, (data, (bounds, crs))):
        (count, height, width) = data.shape

        if 3 > count > 4:
            raise Exception("Source data must be 3 or 4 bands")

        if count == 4:
            raise Exception(
                "Variable opacity (alpha channel) not yet implemented")

        rgb = np.ma.transpose(data.astype(np.uint8), [1, 2, 0])
        if data.mask.any():
            a = np.logical_and.reduce(~data.mask).astype(np.uint8) * 255
        else:
            a = np.full((rgb.shape[:-1]), 255, np.uint8)

        return (np.dstack((rgb, a)), 'RGBA')
