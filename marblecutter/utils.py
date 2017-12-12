# coding=utf-8
from collections import namedtuple

Bounds = namedtuple("Bounds", ["bounds", "crs"])
PixelCollection = namedtuple("PixelCollection", ["data", "bounds", "band"])
PixelCollection.__new__.__defaults__ = (None, )
Source = namedtuple("Source", [
    "url", "name", "resolution", "band_info", "meta", "recipes", "acquired_at",
    "band", "priority", "coverage", "geom"
])
Source.__new__.__defaults__ = ({}, {}, {}, None, None, None, None, None, )
