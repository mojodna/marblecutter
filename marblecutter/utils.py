# coding=utf-8
from collections import namedtuple

import numpy as np

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
        "mask",
        "filename",
        "min_zoom",
        "max_zoom",
        "expr"
    ],
)
Source.__new__.__defaults__ = (
    {}, {}, {}, None, None, None, None, None, None, None, None, None, None
)


def make_colormap(colormap):
    lut = None

    for i, color in colormap.items():
        if lut is None:
            try:
                # color is probably a 4 tuple (but might be smaller)
                dims = len(color)
            except Exception:
                # but for convenience it might be an int
                dims = 1

            if dims == 3:
                # add an alpha channel
                dims = 4

            lut = np.ma.zeros(shape=(256, dims), dtype=np.uint8)
            lut.mask = True

        try:
            if len(color) == 3:
                # set to full opacity
                color = tuple(color) + (255,)
        except Exception:
            pass

        lut[int(i)] = color

    return lut
