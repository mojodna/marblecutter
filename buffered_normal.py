# noqa
# coding=utf-8
from __future__ import division

import logging
from StringIO import StringIO

import numpy as np
from PIL import Image

from normal import render_normal


LOG = logging.getLogger(__name__)

BUFFER = 4
COLLAR = 2
CONTENT_TYPE = 'image/png'
EXT = 'png'
NAME = 'Buffered Normal'


def render(tile, (data, buffers)): # noqa
    buffers = map(lambda x: max(0, x - COLLAR), buffers)
    data = data[0][buffers[3]:data.shape[1] - buffers[1],
                   buffers[0]:data.shape[2] - buffers[2]]

    if buffers[0] == 0:
        # empty left
        cols = data[:, :COLLAR]
        data = np.hstack((data, cols))
        pass

    if buffers[2] == 0:
        # empty right
        cols = data[:, -COLLAR:]
        data = np.hstack((cols, data))
        pass

    if buffers[3] == 0:
        # empty top buffer; repeat
        rows = data[:COLLAR]
        data = np.vstack((rows, data))
        buffers[3] = COLLAR

    if buffers[1] == 0:
        # empty bottom buffer; repeat
        data = np.vstack((data, rows))
        buffers[1] = COLLAR

    imgarr = render_normal(tile, data, buffers)

    out = StringIO()
    im = Image.fromarray(imgarr, 'RGBA')
    im.save(out, 'png')

    return (CONTENT_TYPE, out.getvalue())
