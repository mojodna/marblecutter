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

info=$(rio info $input 2> /dev/null)
count=$(jq .count <<< $info)
height=$(jq .height <<< $info)
width=$(jq .width <<< $info)
zoom=$(get_zoom.py $input)
overviews=""
mask=""

if [ "$count" -eq 4 ]; then
  mask="-mask 4"
fi

>&2 echo "Transcoding bands..."
gdal_translate \
  -b 1 \
  -b 2 \
  -b 3 \
  $mask \
  -co TILED=yes \
  -co COMPRESS=JPEG \
  -co PHOTOMETRIC=YCbCr \
  -co BLOCKXSIZE=512 \
  -co BLOCKYSIZE=512 \
  -co NUM_THREADS=ALL_CPUS \
  $input $output

for z in $(seq 1 $zoom); do
  if [ $[$height / $[2 ** $[$z + 1]]] -lt 1 ]; then
    break
  fi

  overviews="${overviews} $[2 ** $z]"
done

>&2 echo "Adding overviews..."
gdaladdo \
  -r lanczos \
  --config GDAL_TIFF_OVR_BLOCKSIZE 512 \
  --config TILED_OVERVIEW yes \
  --config COMPRESS_OVERVIEW JPEG \
  --config PHOTOMETRIC YCBCR \
  --config BLOCKXSIZE_OVERVIEW 512 \
  --config BLOCKYSIZE_OVERVIEW 512 \
  --config NUM_THREADS_OVERVIEW ALL_CPUS \
  $output \
  $overviews

if [ "$mask" != "" ]; then
  >&2 echo "Adding overviews to mask..."
  gdaladdo \
    --config GDAL_TIFF_OVR_BLOCKSIZE 512 \
    --config TILED_OVERVIEW yes \
    --config COMPRESS_OVERVIEW DEFLATE \
    --config BLOCKXSIZE_OVERVIEW 512 \
    --config BLOCKYSIZE_OVERVIEW 512 \
    --config SPARSE_OK_OVERVIEW yes \
    --config NUM_THREADS_OVERVIEW ALL_CPUS \
    $output.msk \
    $overviews
fi
