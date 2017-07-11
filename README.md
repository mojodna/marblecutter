# Marblecutter

This is a standalone (Python / Flask) and Lambda-based dynamic tiler for S3-hosted GeoTIFFs. It is
also a set of utilities for transcoding and otherwise preparing raster data for rendering by the
tiler.

More information:

* [Introducing the AWS Lambda Tiler](https://hi.stamen.com/stamen-aws-lambda-tiler-blog-post-76fc1138a145#.j644z9qvw)

## Development

Development is best done using [Docker](https://docker.com/), as there are a number of dependencies,
some of which remain unpackaged for common OSes (e.g. GDAL-2.2+).

If you're going to be experimenting with mosaicking in any form, `docker-compose` makes things even
easier, as it packages marblecutter alongside a PostGIS database containing footprints and other
metadata about imagery.

```bash
# build
docker-compose build

# start (requires that Postgres has been populated with appropriate footprint data)
docker-compose up
```

The transcoding and metadata tools can be used from the images built by `docker-compose`:

```bash
docker-compose run web bash
process.sh ...
```

## AWS Lambda / API Gateway

`project.json.hbs` defines an [`apex`](http://apex.run/) project that can be deployed to AWS Lambda.

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
