# coding=utf-8
from __future__ import absolute_import, division, print_function

import numpy as np

from .. import PixelCollection
from .image import Image
from .utils import TransformationBase

IMAGE_TRANSFORMATION = Image()


class Greyscale(TransformationBase):

    def transform(self, pixels):
        data = pixels.data
        (count, _, _) = data.shape

        if count > 1:
            raise Exception("Source data must be 1 band")

        data = np.ma.array([data[0]] * 3)

        return IMAGE_TRANSFORMATION.transform(PixelCollection(data, pixels.bounds))
