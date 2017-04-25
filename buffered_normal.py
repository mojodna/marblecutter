# noqa
# coding=utf-8
from __future__ import division

import logging
from StringIO import StringIO

from PIL import Image

from normal import render_normal


LOG = logging.getLogger(__name__)

BUFFER = 4
COLLAR = 2
CONTENT_TYPE = 'image/png'


def render(tile, (data, buffers)): # noqa
    buffers = map(lambda x: x - COLLAR, buffers)
    data = data[0][buffers[3]:data.shape[1] - buffers[1],
                   buffers[0]:data.shape[2] - buffers[2]]

    imgarr = render_normal(tile, data, buffers)

    out = StringIO()
    im = Image.fromarray(imgarr, 'RGBA')
    im.save(out, 'png')

    return (CONTENT_TYPE, out.getvalue())
