# coding=utf-8
from __future__ import division

import logging
from StringIO import StringIO

import matplotlib
matplotlib.use("Agg")

from matplotlib.colors import LinearSegmentedColormap
import matplotlib.pyplot as plt
import mercantile
import numpy as np
import numpy.ma as ma
from rasterio import Affine
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.warp import reproject

BUFFER = 4


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

GREY_HILLS_RAMP = {
    "red": [(0.0, 0.0, 0.0),
            (0.25, 0.0, 0.0),
            (180 / 255.0, 0.5, 0.5),
            (1.0, 170 / 255.0, 170 / 255.0)],
    "green": [(0.0, 0.0, 0.0),
              (0.25, 0.0, 0.0),
              (180 / 255.0, 0.5, 0.5),
              (1.0, 170 / 255.0, 170 / 255.0)],
    "blue": [(0.0, 0.0, 0.0),
             (0.25, 0.0, 0.0),
             (180 / 255.0, 0.5, 0.5),
             (1.0, 170 / 255.0, 170 / 255.0)],
}

GREY_HILLS = LinearSegmentedColormap("grey_hills", GREY_HILLS_RAMP)

LOG = logging.getLogger(__name__)


def render(tile, (data, buffers)):
    bounds = mercantile.bounds(*tile)
    ll = mercantile.xy(*bounds[0:2])
    ur = mercantile.xy(*bounds[2:4])

    dx = (ur[0] - ll[0]) / 256
    dy = (ur[1] - ll[1]) / 256

    hs = render_hillshade(tile, data[0], buffers, dx, dy)

    out = StringIO()
    plt.imsave(
        out,
        hs,
        cmap=GREY_HILLS,
        vmin=0,
        vmax=255,
        format='png',
    )

    return out.getvalue()

# TODO get scale from entrypoint
def render_hillshade(tile, data, buffers, dx, dy, scale=1, resample=True, add_slopeshade=True):
    bounds = mercantile.bounds(*tile)
    ll = mercantile.xy(*bounds[0:2])
    ur = mercantile.xy(*bounds[2:4])

    dx = -1 * (ur[0] - ll[0]) / 256
    dy = -1 * (ur[1] - ll[1]) / 256

    # TODO slopeshade addition results in excessively dark images

    # interpolate latitudes
    # TODO do this earlier
    bounds = mercantile.bounds(tile.x, tile.y, tile.z)
    height = data.shape[0]
    latitudes = np.interp(np.arange(height), [0, height - 1], [bounds.north, bounds.south])

    factors = 1 / np.cos(np.radians(latitudes))

    # convert to 2d array, rotate 270º, scale data
    data = data * np.rot90(np.atleast_2d(factors), 3)

    resample_factor = RESAMPLING.get(tile.z, 1.0)
    crs = CRS({'init': 'epsg:3857'})
    aff = Affine(dx, 0.0, -20037508.34, 0.0, dy, 20037508.34)

    if resample and resample_factor != 1.0:
        # resample data according to Tom Paterson's chart

        # this is the equivalent of a scale transform (I think)
        newaff = Affine(aff.a / resample_factor, aff.b, aff.c,
                        aff.d, aff.e / resample_factor, aff.f)
        # create an empty target array that's the shape of the resampled tile (e.g. 80% of 260x260px)
        resampled = np.empty(shape=(int(round(data.shape[0] * resample_factor)),
                                 int(round(data.shape[1] * resample_factor))),
                             dtype=data.dtype)
        resampled_mask = np.empty(shape=(resampled.shape))

        # downsample using GDAL's reprojection functionality (which gives us access to different resampling algorithms)
        reproject(
            data,
            resampled,
            src_transform=aff,
            dst_transform=newaff,
            src_crs=crs,
            dst_crs=crs,
            resampling=Resampling.bilinear,
        )

        # reproject / resample the mask so that intermediate operations can also use it
        reproject(
            data.mask.astype(np.uint8),
            resampled_mask,
            src_transform=aff,
            dst_transform=newaff,
            src_crs=crs,
            dst_crs=crs,
            resampling=Resampling.nearest,
        )

        resampled = ma.array(resampled, mask=resampled_mask)

        hs = _hillshade(resampled,
            dx=dx * scale,
            dy=dy * scale,
            vert_exag=EXAGGERATION.get(tile.z, 1.0),
            # azdeg=315, # which direction is the light source coming from (north-south)
            # altdeg=45, # what angle is the light source coming from (overhead-horizon)
        )

        if add_slopeshade:
            ss = slopeshade(resampled,
                dx=dx * scale,
                dy=dy * scale,
                vert_exag=EXAGGERATION.get(tile.z, 1.0)
            )

            hs *= ss

        # scale hillshade values (0.0-1.0) to integers (0-255)
        hs = (255.0 * hs).astype(np.uint8)

        # create an empty target array that's the shape of the target tile + buffers (e.g. 260x260px)
        resampled_hs = np.empty(shape=data.shape, dtype=hs.dtype)

        # upsample (invert the previous reprojection)
        reproject(
            hs.data,
            resampled_hs,
            src_transform=newaff,
            dst_transform=aff,
            src_crs=crs,
            dst_crs=crs,
            resampling=Resampling.bilinear,
        )

        hs = ma.array(resampled_hs, mask=data.mask)
    else:
        hs = _hillshade(data,
            dx=dx * scale,
            dy=dy * scale,
            vert_exag=EXAGGERATION.get(tile.z, 1.0),
            # azdeg=315, # which direction is the light source coming from (north-south)
            # altdeg=45, # what angle is the light source coming from (overhead-horizon)
        )

        if add_slopeshade:
            ss = slopeshade(data,
                dx=dx * scale,
                dy=dy * scale,
                vert_exag=EXAGGERATION.get(tile.z, 1.0)
            )

            # hs *= 0.8
            hs *= ss

        # scale hillshade values (0.0-1.0) to integers (0-255)
        hs = (255.0 * hs).astype(np.uint8)

    (left_buffer, bottom_buffer, right_buffer, top_buffer) = buffers
    return hs[left_buffer:hs.shape[0] - right_buffer, top_buffer:hs.shape[1] - bottom_buffer]


def _hillshade(elevation, azdeg=315, altdeg=45, vert_exag=1, dx=1, dy=1, fraction=1.):
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
