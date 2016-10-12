Transcode source scene:

```bash
gdal_translate \
  -co TILED=yes \
  -co COMPRESS=DEFLATE \
  -co PREDICTOR=2 \
  -co BLOCKXSIZE=512 \
  -co BLOCKYSIZE=512 \
  -co NUM_THREADS=ALL_CPUS \
  /vsicurl/http://hotosm-oam.s3.amazonaws.com/uploads/2016-10-11/57fca69e84ae75bb00ec751f/scene/0/scene-0-image-0-DG-103001005E85AC00.tif \
  scene-0-image-0-DG-103001005E85AC00.tif
```

Add external overviews:

Overview calculation: `Math.floor(Math.log(Math.max(width, height)) / Math.log(2))`

```bash
gdaladdo \
  -r cubic \
  --config GDAL_TIFF_OVR_BLOCKSIZE 512 \
  --config TILED_OVERVIEW yes \
  --config COMPRESS_OVERVIEW DEFLATE \
  --config PREDICTOR_OVERVIEW 2 \
  --config BLOCKXSIZE_OVERVIEW 512 \
  --config BLOCKYSIZE_OVERVIEW 512 \
  --config NUM_THREADS_OVERVIEW ALL_CPUS \
  -ro \
  scene-0-image-0-DG-103001005E85AC00.tif \
  2 4 8 16 32 64 128 256 512 1024 2048 4096 8192 16384 32768 65536
```

Write back to S3:

```bash
aws s3 cp \
  scene-0-image-0-DG-103001005E85AC00.tif \
  s3://oam-dynamic-tiler-tmp/uploads/2016-10-11/57fca69e84ae75bb00ec751f/scene/0/
aws s3 cp \
  scene-0-image-0-DG-103001005E85AC00.tif.ovr \
  s3://oam-dynamic-tiler-tmp/uploads/2016-10-11/57fca69e84ae75bb00ec751f/scene/0/
```

Create warped VRT:

(zoom 19, from `get_zoom.py`)

```bash
gdalwarp \
  /vsicurl/https://s3.amazonaws.com/oam-dynamic-tiler-tmp/uploads/2016-10-11/57fca69e84ae75bb00ec751f/scene/0/scene-0-image-0-DG-103001005E85AC00.tif \
  scene-0-image-0-DG-103001005E85AC00.vrt \
  -r cubic \
  -t_srs epsg:3857 \
  -of VRT \
  -te -20037508.34 -20037508.34 20037508.34 20037508.34 \
  -ts 134217728 134217728 \
  -dstalpha
```

Write back to S3:

```bash
aws s3 cp \
  scene-0-image-0-DG-103001005E85AC00.vrt \
  s3://oam-dynamic-tiler-tmp/uploads/2016-10-11/57fca69e84ae75bb00ec751f/scene/0/
```
