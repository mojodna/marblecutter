#!/usr/bin/env bash

input=$1
output=$2

set -euo pipefail

if [ -z $input ] || [ -z $output ]; then
  # input is an HTTP-accessible GDAL-readable image
  # output is an S3 URI w/o extensions
  # e.g.:
  #   bin/process.sh \
  #   http://hotosm-oam.s3.amazonaws.com/uploads/2016-12-29/58655b07f91c99bd00e9c7ab/scene/0/scene-0-image-0-transparent_image_part2_mosaic_rgb.tif \
  #   s3://oam-dynamic-tiler-tmp/sources/58655b07f91c99bd00e9c7ab/0/58655b07f91c99bd00e9c7a6
  >&2 echo "usage: $(basename $0) <input> <output>"
  exit 1
fi

PATH=$(cd $(dirname "$0"); pwd -P):$PATH
source=$(mktemp)
intermediate=$(mktemp)

# 1. download source
echo "Downloading $input..."
if [[ $input =~ "s3://" ]]; then
  aws s3 cp $input $source
else
  curl -sfL $input -o $source
fi

# 2. transcode + generate overviews
echo "Transcoding..."
transcode.sh $source $intermediate
rm -f $source

# 3. upload TIF
echo "Uploading..."
aws s3 cp $intermediate ${output}.tif --acl public-read
rm -f $intermediate

# 4. create and upload metadata
echo "Generating metadata..."
# TODO make mask optional
get_metadata.py $output | aws s3 cp - ${output}.json

# 5. create and upload warped VRT
echo "Generating warped VRT..."
make_vrt.sh -r lanczos ${output}.tif | aws s3 cp - ${output}.vrt

if [ -f ${intermediate}.msk ]; then
  # 6. upload mask
  echo "Uploading mask..."
  aws s3 cp ${intermediate}.msk ${output}.tif.msk --acl public-read
  rm -f ${intermediate}.msk*

  # 7. create and upload warped VRT for mask
  echo "Generating warped VRT..."
  make_vrt.sh ${output}.tif.msk | aws s3 cp - ${output}_mask.vrt
fi
