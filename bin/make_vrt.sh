#!/usr/bin/env bash

set -eo pipefail

resampling_method="near"

while getopts ":r:" opt; do
  case $opt in
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
  >&2 echo "usage: $(basename $0) [-r resampling method] <image prefix>"
  exit 1
fi

set -u

PATH=$(cd $(dirname "$0"); pwd -P):$PATH

http_source=${source/s3:\/\//http:\/\/s3.amazonaws.com\/}
zoom=$(get_zoom.py ${source})
pixels=$[2 ** ($zoom + 8)]

gdalwarp \
  /vsicurl/${http_source} \
  $output \
  -r $resampling_method \
  -t_srs epsg:3857 \
  -of VRT \
  -te -20037508.34 -20037508.34 20037508.34 20037508.34 \
  -ts $pixels $pixels > /dev/null 2>&1

cat $output
rm -f $output
