# coding=utf-8
from __future__ import absolute_import, division, print_function

import numpy as np
from rasterio.plot import reshape_as_image

from .. import PixelCollection
from .utils import Transformation


class Image(Transformation):

    def transform(self, pixels):
        data = pixels.data
        (count, _, _) = data.shape

        if 3 > count > 4:
            raise Exception("Source data must be 3 or 4 bands")

        if data.dtype == np.float32:
            # data was normalized; expand it
            data *= np.iinfo(np.uint8).max

        if count == 4:
            rgba = reshape_as_image(data.astype(np.uint8))
            return PixelCollection(rgba, pixels.bounds), "RGBA"

        rgb = reshape_as_image(data.astype(np.uint8))
        if data.mask.any():
            a = np.logical_and.reduce(~data.mask).astype(np.uint8) * 255
        else:
            a = np.full((rgb.shape[:-1]), 255, np.uint8)

        return PixelCollection(np.dstack((rgb, a)), pixels.bounds), "RGBA"
