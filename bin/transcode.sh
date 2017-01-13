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

# convert S3 URLs to HTTP
input=$(sed 's|s3://\([^/]*\)/|http://\1.s3.amazonaws.com/|' <<< $input)

info=$(rio info $input 2> /dev/null)
count=$(jq .count <<< $info)
dtype=$(jq -r .dtype <<< $info)
height=$(jq .height <<< $info)
width=$(jq .width <<< $info)
zoom=$(get_zoom.py $input)
overviews=""
mask=""
opts=""
overview_opts=""

# update info now that rasterio has read it
if [[ $input =~ "http://" ]] || [[ $input =~ "https://" ]]; then
  input="/vsicurl/$input"
fi


if [ "$count" -eq 4 ]; then
  mask="-mask 4"
fi

if [ "$dtype" == "uint8" ]; then
  opts="-co COMPRESS=JPEG -co PHOTOMETRIC=YCbCr"
  overview_opts="--config COMPRESS_OVERVIEW JPEG --config PHOTOMETRIC_OVERVIEW YCbCr"
else
  opts="-co COMPRESS=DEFLATE -co PREDICTOR=2"
  overview_opts="--config COMPRESS_OVERVIEW DEFLATE --config PREDICTOR_OVERVIEW 2"
fi

>&2 echo "Transcoding bands..."
gdal_translate \
  -b 1 \
  -b 2 \
  -b 3 \
  $mask \
  -co TILED=yes \
  -co BLOCKXSIZE=512 \
  -co BLOCKYSIZE=512 \
  -co NUM_THREADS=ALL_CPUS \
  $opts \
  $input $output

for z in $(seq 1 $zoom); do
  overviews="${overviews} $[2 ** $z]"

  # stop when overviews fit within a single block (even if they cross)
  if [ $[$height / $[2 ** $[$z]]] -lt 512 ] && [ $[$width / $[2 ** $[$z]]] -lt 512 ]; then
    break
  fi
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
  $overview_opts \
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
