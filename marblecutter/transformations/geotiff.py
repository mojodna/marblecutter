# noqa
# coding=utf-8
from __future__ import absolute_import, division, print_function

# Keeping consistent buffer with other transforms
# so that we can more effectively cache the call to mosaic.compsoite()
BUFFER = 4


def transformation():
    def _transform((data, (bounds, crs))):
        # GeoTIFF transform does nothing.

        return (data, 'raw')

    _transform.buffer = BUFFER
    return _transform
