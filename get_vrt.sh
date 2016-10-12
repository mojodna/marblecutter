#!/usr/bin/env bash

id=$1

>&2 echo "Generating VRT for $id"

set -euo pipefail

zoom=$(python get_zoom.py s3://${S3_BUCKET}/sources/${id}/index.tif)
pixels=$[2 ** ($zoom + 8)]

gdalwarp \
  /vsicurl/https://s3.amazonaws.com/${S3_BUCKET}/sources/${id}/index.tif \
  /vsistdout \
  -r cubic \
  -t_srs epsg:3857 \
  -of VRT \
  -te -20037508.34 -20037508.34 20037508.34 20037508.34 \
  -ts $pixels $pixels \
  -dstalpha
