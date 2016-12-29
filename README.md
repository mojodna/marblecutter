# OpenAerialMap Dynamic Tiler

This is a standalone (Python / Flask) and Lambda-based dynamic tiler for S3-hosted GeoTIFFs.

More information:

* [Introducing the AWS Lambda Tiler](https://hi.stamen.com/stamen-aws-lambda-tiler-blog-post-76fc1138a145#.j644z9qvw)

## Command Line Tools

The command line tools (in `bin/`) require `bash`, `jq`, `python`, and `rasterio`.

Transcode source scene:

```bash
bin/transcode.sh \
  http://hotosm-oam.s3.amazonaws.com/uploads/2016-10-11/57fca69e84ae75bb00ec751f/scene/0/scene-0-image-0-DG-103001005E85AC00.tif \
  57fca69e84ae75bb00ec751f.tif
```

Add external overviews:

```bash
bin/make_overviews.sh 57fca69e84ae75bb00ec751f.tif
```

Write back to S3:

```bash
aws s3 cp \
  57fca69e84ae75bb00ec751f.tif \
  s3://oam-dynamic-tiler-tmp/sources/57fca69e84ae75bb00ec751f/index.tif \
  --acl public-read
aws s3 cp \
  57fca69e84ae75bb00ec751f.tif.ovr \
  s3://oam-dynamic-tiler-tmp/sources/57fca69e84ae75bb00ec751f/index.tif.ovr \
  --acl public-read
```

Create warped VRT and write to S3:

```bash
id=57fc935b84ae75bb00ec751b; bin/make_vrt.sh $id | aws s3 cp - s3://oam-dynamic-tiler-tmp/sources/${id}/index.vrt
```

Generate metadata JSON and write to S3:

```bash
id=57fc935b84ae75bb00ec751b; bin/get_metadata.py $id | aws s3 cp - s3://oam-dynamic-tiler-tmp/sources/${id}/index.json
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

Attach policy to the `tiler_lambda_function` role.

Update `project.json` with `tiler_lambda_function`'s Role ARN, e.g. `arn:aws:iam::670261699094:role/tiler_lambda_function`.

Run `apex deploy`. (Add `-l debug` to see what's running.) This will build the Docker image defined
in `deps/` to produce a `task.zip` containing binary dependencies needed when deploying to the
Lambda runtime.
