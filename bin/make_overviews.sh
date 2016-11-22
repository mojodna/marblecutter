#!/usr/bin/env bash

input=$1

set -euo pipefail

if [ -z $input ]; then
  >&2 echo "usage: $(basename $0) <input>"
  exit 1
fi

PATH=$(cd $(dirname "$0"); pwd -P):$PATH

height=$(rio info $input 2> /dev/null | jq .height)
width=$(rio info $input 2> /dev/null | jq .width)
zoom=$(get_zoom.py $input)
overviews=""

for z in $(seq 1 $zoom); do
  if [ $[$height / $[2 ** $[$z + 1]]] -lt 1 ]; then
    break
  fi

  overviews="${overviews} $[2 ** $z]"
done

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
  $input \
  $overviews
