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
  s3://oam-dynamic-tiler-tmp/sources/57fca69e84ae75bb00ec751f/index.tif
aws s3 cp \
  scene-0-image-0-DG-103001005E85AC00.tif.ovr \
  s3://oam-dynamic-tiler-tmp/sources/57fca69e84ae75bb00ec751f/index.tif
```

Create warped VRT and write to S3:

```bash
id=57fc935b84ae75bb00ec751b; ./get_vrt.sh $id | aws s3 cp - s3://oam-dynamic-tiler-tmp/sources/${id}/index.vrt
```

Generate metadata JSON and write to S3:

```bash
id=57fc935b84ae75bb00ec751b; python get_metadata.py $id | aws s3 cp - s3://oam-dynamic-tiler-tmp/sources/${id}/index.json
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
