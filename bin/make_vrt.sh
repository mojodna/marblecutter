#!/usr/bin/env bash

set -eo pipefail

resampling_method="near"
dstalpha=""

while getopts ":r:a" opt; do
  case $opt in
    a)
      dstalpha="-dstalpha"
      ;;
    r)
      resampling_method=$OPTARG
      ;;
    \?)
      >&2 echo "Invalid option: -$OPTARG"
      ;;
  esac
done

shift $((OPTIND - 1))

source=$1
output=$(mktemp)

if [ -z $source ]; then
  >&2 echo "usage: $(basename $0) [-r resampling method] [-a] <image prefix>"
  exit 1
fi

set -u

PATH=$(cd $(dirname "$0"); pwd -P):$PATH

zoom=$(get_zoom.py ${source})
pixels=$[2 ** ($zoom + 8)]

if [[ "$source" =~ https?:// ]]; then
  gdal_source="/vsicurl/${source}"
elif [[ "$source" =~ s3:// ]]; then
  gdal_source=$(sed 's|s3://\([^/]*\)/|/vsis3/\1/|' <<< $source)
fi

gdalwarp \
  ${gdal_source} \
  $output \
  -r $resampling_method \
  $dstalpha \
  -t_srs epsg:3857 \
  -of VRT \
  -te -20037508.34 -20037508.34 20037508.34 20037508.34 \
  -ts $pixels $pixels > /dev/null 2>&1

cat $output
rm -f $output
