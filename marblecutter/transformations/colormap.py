# coding=utf-8
from __future__ import absolute_import, division, print_function

import numpy as np

from .. import PixelCollection
from ..utils import make_colormap
from .image import Image
from .utils import Transformation

IMAGE_TRANSFORMATION = Image()


class Colormap(Transformation):

    def __init__(self, colormap):
        super(Colormap, self).__init__()

        self.lut = make_colormap(colormap)

    def transform(self, pixels):
        data = pixels.data
        (count, _, _) = data.shape

        if count > 1:
            raise Exception("Source data must be 1 band")

        # stash the mask
        mask = data.mask

        # apply the color map
        data = self.lut[data[0], :]

        # re-shape to match band-style
        data = np.ma.transpose(data, [2, 0, 1])

        # re-apply the mask
        data.mask = mask

        return IMAGE_TRANSFORMATION.transform(PixelCollection(data, pixels.bounds))
