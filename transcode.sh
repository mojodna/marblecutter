#!/usr/bin/env bash

input=$1
output=$2

# TODO validate input
# TODO support local files (not just http(s))

set -euo pipefail

gdal_translate \
  -co TILED=yes \
  -co COMPRESS=DEFLATE \
  -co PREDICTOR=2 \
  -co BLOCKXSIZE=512 \
  -co BLOCKYSIZE=512 \
  -co NUM_THREADS=ALL_CPUS \
  /vsicurl/$input \
  $output
