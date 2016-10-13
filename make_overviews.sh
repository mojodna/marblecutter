#!/usr/bin/env bash

input=$1

# TODO validate input

set -euo pipefail

# TODO calculate overviews using the same approach as get_vrt.sh
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
  2 4 8 16 32 64 128 256 512 1024 2048 4096 8192 16384 32768 65536
