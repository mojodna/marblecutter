#!/usr/bin/env bash

# capture arguments (we'll pass them to oin-meta-generator)
args=("${@:1:$[$#-2]}")
args=${args:-""}
shift $[$#-2]

input=$1
output=$2
# target size in KB
THUMBNAIL_SIZE=${THUMBNAIL_SIZE:-300}
TILER_BASE_URL=${TILER_BASE_URL:-http://tiles.openaerialmap.org}

set -euo pipefail

to_clean=()

function cleanup() {
  for f in ${to_clean[@]}; do
    rm -f "${f}"
  done
}

function cleanup_on_failure() {
  s3_outputs=(${output}.tif ${output}.tif.msk ${output}_footprint.json ${output}.vrt ${output}_thumb.png ${output}.json)

  set +e
  for x in ${s3_outputs[@]}; do
    aws s3 rm $x 2> /dev/null
  done
  set -e

  cleanup
}

if [[ -z "$input" || -z "$output" ]]; then
  # input is an HTTP-accessible GDAL-readable image
  # output is an S3 URI w/o extensions
  # e.g.:
  #   bin/process.sh \
  #   http://hotosm-oam.s3.amazonaws.com/uploads/2016-12-29/58655b07f91c99bd00e9c7ab/scene/0/scene-0-image-0-transparent_image_part2_mosaic_rgb.tif \
  #   s3://oam-dynamic-tiler-tmp/sources/58655b07f91c99bd00e9c7ab/0/58655b07f91c99bd00e9c7a6
  >&2 echo "usage: $(basename $0) <input> <output>"
  exit 1
fi

set +u

# attempt to load credentials from an IAM profile if none were provided
if [[ -z "$AWS_ACCESS_KEY_ID"  || -z "$AWS_SECRET_ACCESS_KEY" ]]; then
  set +e

  role=$(curl -sf --connect-timeout 1 http://169.254.169.254/latest/meta-data/iam/security-credentials/)
  credentials=$(curl -sf --connect-timeout 1 http://169.254.169.254/latest/meta-data/iam/security-credentials/${role})
  export AWS_ACCESS_KEY_ID=$(jq -r .AccessKeyId <<< $credentials)
  export AWS_SECRET_ACCESS_KEY=$(jq -r .SecretAccessKey <<< $credentials)
  export AWS_SESSION_TOKEN=$(jq -r .Token <<< $credentials)

  set -e
fi

set -u

trap cleanup EXIT
trap cleanup_on_failure INT
trap cleanup_on_failure ERR

__dirname=$(cd $(dirname "$0"); pwd -P)
PATH=$__dirname:${__dirname}/../node_modules/.bin:$PATH
filename=$(basename $input)
base=$(mktemp)
source="${base}.${filename}"
to_clean+=($source)
intermediate=${base}-intermediate.tif
to_clean+=($intermediate)
gdal_output=$(sed 's|s3://\([^/]*\)/|/vsis3/\1/|' <<< $output)
tiler_url=$(sed "s|s3://[^/]*|${TILER_BASE_URL}|" <<< $output)

>&2 echo "Processing ${input} to ${output}..."

# 0. download source (if appropriate)
if [[ "$input" =~ ^s3:// ]]; then
  if [[ "$input" =~ \.zip$ || "$input" =~ \.tar\.gz$ ]]; then
    >&2 echo "Downloading $input from S3..."
    aws s3 cp $input $source
  else
    source=$input
  fi
elif [[ "$input" =~ s3\.amazonaws\.com ]]; then
  if [[ "$input" =~ \.zip$ || "$input" =~ \.tar\.gz$ ]]; then
    >&2 echo "Downloading $input from S3 over HTTP..."
    curl -sfL $input -o $source
  else
    source=$input
  fi
else
  >&2 echo "Downloading $input..."
  curl -sfL $input -o $source
fi

# 1. transcode + generate overviews
>&2 echo "Transcoding..."
transcode.sh $source $intermediate
rm -f $source

# # 2. generate metadata
# >&2 echo "Generating OIN metadata..."
# if [[ ${#args} -gt 0 ]]; then
#   metadata=$(oin-meta-generator -u "${output}.tif" -m "thumbnail=${output}_thumb.png" -m "tms=${tiler_url}/{z}/{x}/{y}.png" -m "wmts=${tiler_url}/wmts" "${args[@]}" $intermediate)
# else
#   metadata=$(oin-meta-generator -u "${output}.tif" -m "thumbnail=${output}_thumb.png" -m "tms=${tiler_url}/{z}/{x}/{y}.png" -m "wmts=${tiler_url}/wmts" $intermediate)
# fi

# 2. upload TIF
>&2 echo "Uploading..."
aws s3 cp $intermediate ${output}.tif

if [ -f ${intermediate}.msk ]; then
  mask=1

  # 3. upload mask
  >&2 echo "Uploading mask..."
  aws s3 cp ${intermediate}.msk ${output}.tif.msk

  # # 4. create RGBA VRT (for use in QGIS, etc.)
  # info=$(rio info $intermediate 2> /dev/null)
  # count=$(jq .count <<< $info)
  # if [ "$count" -eq 4 ]; then
  #   >&2 echo "Generating RGBA VRT..."
  #   vrt=${base}.vrt
  #   to_clean+=($vrt)
  #   gdal_translate \
  #     -b 1 \
  #     -b 2 \
  #     -b 3 \
  #     -b mask \
  #     -of VRT \
  #     ${gdal_output}.tif $vrt
  # else
  #   >&2 echo "Generating VRT..."
  #   vrt=${base}.vrt
  #   to_clean+=($vrt)
  #   gdal_translate \
  #     -of VRT \
  #     ${gdal_output}.tif $vrt
  # fi
  #
  # cat $vrt | \
  #   perl -pe 's|(band="4"\>)|$1\n    <ColorInterp>Alpha</ColorInterp>|' | \
  #   perl -pe "s|${gdal_output}|$(basename $output)|" | \
  #   perl -pe 's|(relativeToVRT=)"0"|$1"1"|' | \
  #   aws s3 cp - ${output}.vrt
else
  mask=0

  # # 3. create RGB VRT (for parity)
  # >&2 echo "Generating RGB VRT..."
  # vrt=${base}.vrt
  # to_clean+=($vrt)
  # gdal_translate \
  #   -of VRT \
  #   ${gdal_output}.tif $vrt
  #
  # cat $vrt | \
  #   perl -pe "s|${gdal_output}|$(basename $output)|" | \
  #   perl -pe 's|(relativeToVRT=)"0"|$1"1"|' | \
  #   aws s3 cp - ${output}.vrt
fi

# # 6. create thumbnail
# >&2 echo "Generating thumbnail..."
# thumb=${base}_thumb.png
# to_clean+=($thumb ${thumb}.aux.xml)
# info=$(rio info $vrt 2> /dev/null)
# count=$(jq .count <<< $info)
# height=$(jq .height <<< $info)
# width=$(jq .width <<< $info)
# target_pixel_area=$(bc -l <<< "$THUMBNAIL_SIZE * 1000 / 0.75")
# ratio=$(bc -l <<< "sqrt($target_pixel_area / ($width * $height))")
# target_width=$(printf "%.0f" $(bc -l <<< "$width * $ratio"))
# target_height=$(printf "%.0f" $(bc -l <<< "$height * $ratio"))
# gdal_translate -of png $vrt $thumb -outsize $target_width $target_height
# aws s3 cp $thumb ${output}_thumb.png
# rm -f $vrt $thumb

# 9. create and upload metadata
>&2 echo "Generating metadata..."
if [ "$mask" -eq 1 ]; then
  meta=$(get_metadata.py --include-mask "${args[@]}" $output)
else
  meta=$(get_metadata.py "${args[@]}" $output)
fi
echo $meta | aws s3 cp - ${output}.json

# 5. create footprint
>&2 echo "Generating footprint..."
info=$(rio info $intermediate)
# resample using 'average' so that rescaled pixels containing _some_ values
# don't end up as NODATA
gdalwarp -r average \
  -ts $[$(jq -r .width <<< $info) / 100] $[$(jq -r .height <<< $info) / 100] \
  -srcnodata $(jq -r .nodata <<< $info) \
  $intermediate ${intermediate/.tif/_small.tif}
rio shapes --mask --as-mask --precision 6 ${intermediate/.tif/_small.tif} | \
  rio_shapes_to_multipolygon.py --argfloat resolution=$(jq .meta.resolution <<< $meta) --argstr filename="$(basename $output).tif" | \
  aws s3 cp - ${output}_footprint.json

rm -f ${intermediate}*

# # 10. Upload OIN metadata
# aws s3 cp - ${output}_meta.json <<< $metadata

# 11. Insert into footprints database
if [[ -z ${DATABASE_URL+x} ]]; then
  >&2 echo "Skipping footprint load because DATABASE_URL is not set"
else
  ingest_single_footprint.sh ${output}_footprint.json | psql $DATABASE_URL
fi

>&2 echo "Done."
