# coding=utf-8
from __future__ import division

import logging
from StringIO import StringIO

import numpy as np
from PIL import Image

# include buffers so that interpolation occurs properly
BUFFER = 4
LOG = logging.getLogger(__name__)


def render(tile, (data, buffers)):
    # we want the output to be 3-channels R, G, B with:
    #   uheight = height + 32768.0
    #   R = int(height) / 256
    #   G = int(height) % 256
    #   B = int(frac(height) * 256)
    # For nodata, we'll use R=0, which corresponds to height < 32,513 which is
    # lower than any depth on Earth.

    # crop image since we don't care about buffers
    pixels = data[0][buffers[0]:data.shape[0] - buffers[2], buffers[1]:data.shape[1] - buffers[3]]
    # pixels = data[0]
    pixels.fill_value = 0

    # transform to uheight, clamping the range
    pixels += 32768.0
    np.clip(pixels, 0.0, 65535.0, out=pixels)

    r = (pixels / 256).astype(np.uint8)
    g = (pixels % 256).astype(np.uint8)
    b = ((pixels * 256) % 256).astype(np.uint8)

    out = StringIO()
    im = Image.fromarray(np.dstack((r, g, b)), 'RGB')
    im.save(out, 'png')

    return ('image/png', out.getvalue())
