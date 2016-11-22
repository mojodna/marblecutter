#!/usr/bin/env bash

input=$1
output=$2

set -euo pipefail

if [ -z $input ]; then
  >&2 echo "usage: $(basename $0) <input> [output]"
  exit 1
fi

if [ -z $output ]; then
  output=$(basename $input)
fi

if [[ $input =~ "http://" ]] || [[ $input =~ "https://" ]]; then
  input="/vsicurl/$input"
fi

gdal_translate \
  -co TILED=yes \
  -co COMPRESS=DEFLATE \
  -co PREDICTOR=2 \
  -co BLOCKXSIZE=512 \
  -co BLOCKYSIZE=512 \
  -co NUM_THREADS=ALL_CPUS \
  $input \
  $output
