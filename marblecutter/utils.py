# coding=utf-8
from collections import namedtuple

Bounds = namedtuple("Bounds", ["bounds", "crs"])
# TODO add colorinterp and copy from src.colorinterp
PixelCollection = namedtuple("PixelCollection", ["data", "bounds", "band", "colormap"])
PixelCollection.__new__.__defaults__ = (None, None)
Source = namedtuple(
    "Source",
    [
        "url",
        "name",
        "resolution",
        "band_info",
        "meta",
        "recipes",
        "acquired_at",
        "band",
        "priority",
        "coverage",
        "geom",
        "filename",
        "min_zoom",
        "max_zoom",
    ],
)
Source.__new__.__defaults__ = (
    {}, {}, {}, None, None, None, None, None, None, None, None
)
