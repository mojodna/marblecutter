# noqa
# coding=utf-8
from __future__ import absolute_import, print_function

from StringIO import StringIO

import matplotlib

# pick a matplotlib backend to pre-empt loading addition modules
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap


CONTENT_TYPES = {
    "png": "image/png",
}

GREY_HILLS_RAMP = {
    "red": [(0.0, 0.0, 0.0), (0.25, 0.0, 0.0), (180 / 255.0, 0.5, 0.5),
            (1.0, 170 / 255.0, 170 / 255.0)],
    "green": [(0.0, 0.0, 0.0), (0.25, 0.0, 0.0), (180 / 255.0, 0.5, 0.5),
              (1.0, 170 / 255.0, 170 / 255.0)],
    "blue": [(0.0, 0.0, 0.0), (0.25, 0.0, 0.0), (180 / 255.0, 0.5, 0.5),
             (1.0, 170 / 255.0, 170 / 255.0)],
}

GREY_HILLS = LinearSegmentedColormap("grey_hills", GREY_HILLS_RAMP)


def ColorRamp(output_format="png", colormap=GREY_HILLS):
    def _format((data, (data_bounds, data_crs)), data_format):
        if data_format is not "raw":
            raise Exception("raw data is required")

        if data.dtype != np.uint8:
            raise Exception("data must be uint8")

        out = StringIO()
        plt.imsave(
            out,
            data[0],
            cmap=colormap,
            vmin=0,
            vmax=255,
            format=output_format)

        return (CONTENT_TYPES[output_format], out.getvalue())

    return _format
