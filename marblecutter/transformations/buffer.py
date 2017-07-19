# noqa
# coding=utf-8
from __future__ import absolute_import

from .utils import TransformationBase


class Buffer(TransformationBase):
    def __init__(self, buffer=0):
        self.buffer = buffer

    def postprocess(self, (data, (bounds, data_crs)), data_format, offsets):
        # don't crop
        return (data, (bounds, data_crs))
