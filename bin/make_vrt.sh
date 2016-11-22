#!/usr/bin/env bash

set -eo pipefail

id=$1
output=$(mktemp)

if [ -z $id ]; then
  >&2 echo "usage: $(basename $0) <scene id>"
  exit 1
fi

if [ -z $S3_BUCKET ]; then
  >&2 echo "S3_BUCKET must be set."
  exit 1
fi

set -u

PATH=$(cd $(dirname "$0"); pwd -P):$PATH

zoom=$(get_zoom.py s3://${S3_BUCKET}/sources/${id}/index.tif)
pixels=$[2 ** ($zoom + 8)]
bands=$(curl -sf https://s3.amazonaws.com/${S3_BUCKET}/sources/${id}/index.json | jq .meta.bandCount)

dstalpha=""

if [ $bands == 3 ]; then
  # create an alpha band
  dstalpha="-dstalpha"
fi

gdalwarp \
  /vsicurl/https://s3.amazonaws.com/${S3_BUCKET}/sources/${id}/index.tif \
  $output \
  -r cubic \
  -t_srs epsg:3857 \
  -of VRT \
  -te -20037508.34 -20037508.34 20037508.34 20037508.34 \
  -ts $pixels $pixels \
  $dstalpha > /dev/null 2>&1

cat $output
rm -f $output
