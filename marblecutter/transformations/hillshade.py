# noqa
# coding=utf-8
from __future__ import absolute_import, division, print_function

import numpy as np

from rasterio import transform, warp
from rasterio.warp import Resampling

from .. import get_resolution_in_meters, get_zoom
from .utils import TransformationBase, apply_latitude_adjustments

# from http://www.shadedrelief.com/web_relief/
EXAGGERATION = {
    0: 45.0,
    1: 29.0,
    2: 20.0,
    3: 14.0,
    4: 9.5,
    5: 6.5,
    6: 5.0,
    7: 3.6,
    8: 2.7,
    9: 2.1,
    10: 1.7,
    11: 1.4,
    12: 1.3,
    13: 1.2,
    14: 1.1,
}

RESAMPLING = {
    5: 0.9,
    6: 0.8,
    7: 0.8,
    8: 0.7,
    9: 0.7,
    10: 0.7,
    11: 0.8,
    12: 0.8,
    13: 0.9,
}


class Hillshade(TransformationBase):
    buffer = 4

    def __init__(self, resample=True, add_slopeshade=True):
        TransformationBase.__init__(self)
        self.resample = resample
        self.add_slopeshade = add_slopeshade

    def transform(self, (data, (bounds, crs))):
        (count, height, width) = data.shape

        if count != 1:
            raise Exception("Can't hillshade from multiple bands")

        (dx, dy) = get_resolution_in_meters((bounds, crs), (height, width))
        zoom = get_zoom(max(dx, dy))
        # invert resolutions for hillshading purposes
        dy *= -1

        data = apply_latitude_adjustments(data, (bounds, crs))

        resample_factor = RESAMPLING.get(zoom, 1.0)
        aff = transform.from_bounds(*bounds, width=width, height=height)

        if self.resample and resample_factor != 1.0:
            # resample data according to Tom Paterson's chart

            # create an empty target array that's the shape of the resampled
            # tile (e.g. 80% of 260x260px)
            resampled_height = int(round(height * resample_factor))
            resampled_width = int(round(width * resample_factor))
            resampled = np.empty(
                shape=(resampled_height, resampled_width), dtype=data.dtype)
            resampled_mask = np.empty(shape=(resampled.shape))

            newaff = transform.from_bounds(
                *bounds, width=resampled_width, height=resampled_height)

            # downsample using GDAL's reprojection functionality (which gives
            # us access to different resampling algorithms)
            warp.reproject(
                data,
                resampled,
                src_transform=aff,
                dst_transform=newaff,
                src_crs=crs,
                dst_crs=crs,
                resampling=Resampling.bilinear, )

            # reproject / resample the mask so that intermediate operations
            # can also use it
            if np.any(data.mask):
                warp.reproject(
                    data.mask.astype(np.uint8),
                    resampled_mask,
                    src_transform=aff,
                    dst_transform=newaff,
                    src_crs=crs,
                    dst_crs=crs,
                    resampling=Resampling.nearest, )

                resampled = np.ma.masked_array(resampled, mask=resampled_mask)
            else:
                resampled = np.ma.masked_array(resampled)

            hs = _hillshade(
                resampled,
                dx=dx,
                dy=dy,
                vert_exag=EXAGGERATION.get(zoom, 1.0), )

            if self.add_slopeshade:
                ss = slopeshade(
                    resampled,
                    dx=dx,
                    dy=dy,
                    vert_exag=EXAGGERATION.get(zoom, 1.0))

                hs *= ss

            # scale hillshade values (0.0-1.0) to integers (0-255)
            hs = (255.0 * hs).astype(np.uint8)

            # create an empty target array that's the shape of the target tile
            # + buffers (e.g. 260x260px)
            resampled_hs = np.empty(shape=data.shape, dtype=hs.dtype)

            # upsample (invert the previous reprojection)
            warp.reproject(
                hs.data,
                resampled_hs,
                src_transform=newaff,
                dst_transform=aff,
                src_crs=crs,
                dst_crs=crs,
                resampling=Resampling.bilinear, )

            hs = np.ma.masked_array(resampled_hs, mask=data.mask)
        else:
            hs = _hillshade(
                data[0],
                dx=dx,
                dy=dy,
                vert_exag=EXAGGERATION.get(zoom, 1.0), )

            if self.add_slopeshade:
                ss = slopeshade(
                    data[0],
                    dx=dx,
                    dy=dy,
                    vert_exag=EXAGGERATION.get(zoom, 1.0))

                # hs *= 0.8
                hs *= ss

            hs = np.ma.masked_array(hs[np.newaxis], mask=data.mask)

            # scale hillshade values (0.0-1.0) to integers (0-255)
            hs = (255.0 * hs).astype(np.uint8)

        hs.fill_value = 0

        return (hs, "raw")


def _hillshade(elevation,
               azdeg=315,
               altdeg=45,
               vert_exag=1,
               dx=1,
               dy=1,
               fraction=1.):
    """
    This is a slightly modified version of
    matplotlib.colors.LightSource.hillshade, modified to remove the contrast
    stretching (because that uses local min/max values).
    Calculates the illumination intensity for a surface using the defined
    azimuth and elevation for the light source.
    Imagine an artificial sun placed at infinity in some azimuth and
    elevation position illuminating our surface. The parts of the surface
    that slope toward the sun should brighten while those sides facing away
    should become darker.
    Parameters
    ----------
    elevation : array-like
        A 2d array (or equivalent) of the height values used to generate an
        illumination map
    azdeg : number, optional
        The azimuth (0-360, degrees clockwise from North) of the light
        source. Defaults to 315 degrees (from the northwest).
    altdeg : number, optional
        The altitude (0-90, degrees up from horizontal) of the light
        source.  Defaults to 45 degrees from horizontal.
    vert_exag : number, optional
        The amount to exaggerate the elevation values by when calculating
        illumination. This can be used either to correct for differences in
        units between the x-y coordinate system and the elevation
        coordinate system (e.g. decimal degrees vs meters) or to exaggerate
        or de-emphasize topographic effects.
    dx : number, optional
        The x-spacing (columns) of the input *elevation* grid.
    dy : number, optional
        The y-spacing (rows) of the input *elevation* grid.
    fraction : number, optional
        Increases or decreases the contrast of the hillshade.  Values
        greater than one will cause intermediate values to move closer to
        full illumination or shadow (and clipping any values that move
        beyond 0 or 1). Note that this is not visually or mathematically
        the same as vertical exaggeration.
    Returns
    -------
    intensity : ndarray
        A 2d array of illumination values between 0-1, where 0 is
        completely in shadow and 1 is completely illuminated.
    """
    # Azimuth is in degrees clockwise from North. Convert to radians
    # counterclockwise from East (mathematical notation).
    az = np.radians(90 - azdeg)
    alt = np.radians(altdeg)

    # Calculate the intensity from the illumination angle
    dy, dx = np.gradient(vert_exag * elevation, dy, dx)
    # The aspect is defined by the _downhill_ direction, thus the negative
    aspect = np.arctan2(-dy, -dx)
    slope = 0.5 * np.pi - np.arctan(np.hypot(dx, dy))
    intensity = (np.sin(alt) * np.sin(slope) +
                 np.cos(alt) * np.cos(slope) * np.cos(az - aspect))

    # Apply contrast stretch
    intensity *= fraction

    intensity = np.clip(intensity, 0, 1, intensity)

    return intensity


def slopeshade(elevation, vert_exag=1, dx=1, dy=1):
    # Calculate the intensity from the illumination angle
    dy, dx = np.gradient(vert_exag * elevation, dy, dx)

    slope = 0.5 * np.pi - np.arctan(np.hypot(dx, dy))

    slope *= (1 / (np.pi / 2))

    return slope
