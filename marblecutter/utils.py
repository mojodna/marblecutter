# coding=utf-8
from collections import namedtuple

Bounds = namedtuple('Bounds', ['bounds', 'crs'])
PixelCollection = namedtuple('PixelCollection', ['data', 'bounds'])
