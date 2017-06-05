# noqa
# coding=utf-8
from __future__ import absolute_import, division, print_function

import numpy as np


def transformation():
    def _transform((data, (bounds, crs))):
        (count, height, width) = data.shape

        if count != 1:
            raise Exception("Can't encode heights from multiple bands")

        # we want the output to be 3-channels R, G, B with:
        #   uheight = height + 32768.0
        #   R = int(height) / 256
        #   G = int(height) % 256
        #   B = int(frac(height) * 256)
        # For nodata, we'll use R=0, which corresponds to height < 32,513 which is
        # lower than any depth on Earth.

        pixels = data[0]
        pixels.fill_value = 0

        # transform to uheight, clamping the range
        pixels += 32768.0
        np.clip(pixels, 0.0, 65535.0, out=pixels)

        r = (pixels / 256).astype(np.uint8)
        g = (pixels % 256).astype(np.uint8)
        b = ((pixels * 256) % 256).astype(np.uint8)

        return (np.dstack((r, g, b)), 'RGB')

    return _transform
