# coding=utf-8
from collections import namedtuple

Bounds = namedtuple('Bounds', ['bounds', 'crs'])
Source = namedtuple('Source',
                    ['url', 'name', 'resolution', 'band', 'meta', 'recipes'])


class PixelCollection(
        namedtuple('PixelCollection', ['data', 'bounds', 'band'])):
    __slots__ = ()

    def __new__(cls, data, bounds, band=None):
        return super(PixelCollection, cls).__new__(cls, data, bounds, band)
