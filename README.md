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

Write to S3:

```bash
aws s3 cp \
  scene-0-image-0-DG-103001005E85AC00.vrt \
  s3://oam-dynamic-tiler-tmp/uploads/2016-10-11/57fca69e84ae75bb00ec751f/scene/0/
```

Generate metadata JSON.

```json
{
  "bounds": [
    -74.2369160,
     18.5141228,
    -74.0413656,
     18.7300648
  ],
  "maxzoom": 22,
  "meta": {
    "approximateZoom": 19,
    "bandCount": 4,
    "height": 48117,
    "source": "/vsicurl/https://s3.amazonaws.com/oam-dynamic-tiler-tmp/uploads/2016-10-11/57fca69e84ae75bb00ec751f/scene/0/scene-0-image-0-DG-103001005E85AC00.vrt",
    "width": 43574
  },
  "minzoom": 12,
  "name": "57fca69e84ae75bb00ec751f",
  "tilejson": "2.1.0"
}
```

Write to S3:

```bash
aws s3 cp \
  index.json \
  s3://oam-dynamic-tiler-tmp/uploads/2016-10-11/57fca69e84ae75bb00ec751f/
```

## lambda

Create IAM role: `tiler_lambda_function` with Trust Relationship policy document:

```xml
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Create IAM policy: `tiler_lambda_logs` with policy document:

```xml
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Action": [
                "logs:*"
            ],
            "Effect": "Allow",
            "Resource": "*"
        }
    ]
}
```

Attach policy to `tiler_lambda_function` role.

Create inline policy to allow `tiler_lambda_function` to write to S3:

```xml
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:PutObjectAcl"
            ],
            "Resource": [
                "arn:aws:s3:::oam-dynamic-tiler-tmp/*"
            ]
        }
    ]
}
```

Update `project.json` with `tiler_lambda_function`'s Role ARN, e.g. `arn:aws:iam::670261699094:role/tiler_lambda_function`.

Run `apex deploy`. (Add `-l debug` to see what's running.) This will build the Docker image defined
in `deps/` to produce a `task.zip` containing binary dependencies needed when deploying to the
Lambda runtime.
