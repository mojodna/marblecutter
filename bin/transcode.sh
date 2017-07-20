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

ext=${input##*.}

if [[ "$ext" == "zip" ]]; then
  # assume it's a zipped TIFF
  inner_source=$(unzip -ql ${input} | grep "tif$\|dem$" | head -1 | awk '{print $4}')

  if [[ -z "$inner_source" ]]; then
    >&2 echo "Could not find a TIFF inside ${input}"
    exit 1
  fi

  input="zip://${input}!${inner_source}"
elif [[ "$input" =~ \.tar\.gz$ ]]; then
  inner_source=$(tar ztf ${input} | grep "tif$" | head -1)

  if [[ -z "$inner_source" ]]; then
    >&2 echo "Could not find a TIFF inside ${input}"
    exit 1
  fi

  input="tar://${input}!${inner_source}"
fi

echo "Transcoding ${input}"

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
bands=""
intermediate=$(mktemp --suffix ".tif")

# update info now that rasterio has read it
if [[ $input =~ "http://" ]] || [[ $input =~ "https://" ]]; then
  input="/vsicurl/$input"
elif [[ $input =~ "s3://" ]]; then
  input=$(sed 's|s3://\([^/]*\)/|/vsis3/\1/|' <<< $input)
elif [[ $input =~ "zip://" ]]; then
  input=$(sed 's|zip://\(.*\)!\(.*\)|/vsizip/\1/\2|' <<< $input)
elif [[ $input =~ "tar://" ]]; then
  input=$(sed 's|tar://\(.*\)!\(.*\)|/vsitar/\1/\2|' <<< $input)
fi


if [ "$count" -eq 4 ]; then
  mask="-mask 4"
else
  mask="-mask mask"
fi

if [ "$dtype" == "uint8" ]; then
  opts="-co COMPRESS=JPEG -co PHOTOMETRIC=YCbCr"
  overview_opts="--config COMPRESS_OVERVIEW JPEG --config PHOTOMETRIC_OVERVIEW YCbCr"
elif [[ "$dtype" =~ "float" ]]; then
  opts="-co COMPRESS=DEFLATE -co PREDICTOR=3"
  overview_opts="--config COMPRESS_OVERVIEW DEFLATE --config PREDICTOR_OVERVIEW 3"
else
  opts="-co COMPRESS=DEFLATE -co PREDICTOR=2"
  overview_opts="--config COMPRESS_OVERVIEW DEFLATE --config PREDICTOR_OVERVIEW 2"
fi

for b in $(seq 1 $count); do
  if [ "$b" -eq 4 ]; then
    break
  fi

  bands="$bands -b $b"
done

>&2 echo "Transcoding bands..."
timeout --foreground 1h gdal_translate \
  $bands \
  $mask \
  -co TILED=yes \
  -co BLOCKXSIZE=512 \
  -co BLOCKYSIZE=512 \
  -co NUM_THREADS=ALL_CPUS \
  $opts \
  $input $intermediate

for z in $(seq 1 $zoom); do
  overviews="${overviews} $[2 ** $z]"

  # stop when overviews fit within a single block (even if they cross)
  if [ $[$height / $[2 ** $[$z]]] -lt 512 ] && [ $[$width / $[2 ** $[$z]]] -lt 512 ]; then
    break
  fi
done

>&2 echo "Adding overviews..."
timeout --foreground 1h gdaladdo \
  -r lanczos \
  --config GDAL_TIFF_OVR_BLOCKSIZE 512 \
  --config TILED_OVERVIEW yes \
  --config BLOCKXSIZE_OVERVIEW 512 \
  --config BLOCKYSIZE_OVERVIEW 512 \
  --config NUM_THREADS_OVERVIEW ALL_CPUS \
  $overview_opts \
  $intermediate \
  $overviews

>&2 echo "Creating cloud-optimized GeoTIFF..."
timeout --foreground 1h gdal_translate \
  $bands \
  $mask \
  -co TILED=yes \
  -co BLOCKXSIZE=512 \
  -co BLOCKYSIZE=512 \
  -co NUM_THREADS=ALL_CPUS \
  $opts \
  $overview_opts \
  -co COPY_SRC_OVERVIEWS=YES \
  --config GDAL_TIFF_OVR_BLOCKSIZE 512 \
  $intermediate $output

if [ "$mask" != "" ]; then
  >&2 echo "Adding overviews to mask..."
  timeout --foreground 1h gdaladdo \
    --config GDAL_TIFF_OVR_BLOCKSIZE 512 \
    --config TILED_OVERVIEW yes \
    --config COMPRESS_OVERVIEW DEFLATE \
    --config BLOCKXSIZE_OVERVIEW 512 \
    --config BLOCKYSIZE_OVERVIEW 512 \
    --config SPARSE_OK_OVERVIEW yes \
    --config NUM_THREADS_OVERVIEW ALL_CPUS \
    ${intermediate}.msk \
    $overviews

  >&2 echo "Creating cloud-optimized GeoTIFF (mask)..."
  timeout --foreground 1h gdal_translate \
    -co TILED=yes \
    -co BLOCKXSIZE=512 \
    -co BLOCKYSIZE=512 \
    -co NUM_THREADS=ALL_CPUS \
    -co COPY_SRC_OVERVIEWS=YES \
    -co COMPRESS=DEFLATE \
    -co PREDICTOR=2 \
    --config GDAL_TIFF_OVR_BLOCKSIZE 512 \
    ${intermediate}.msk ${output}.msk
fi

rm -f $intermediate ${intermediate}.msk
