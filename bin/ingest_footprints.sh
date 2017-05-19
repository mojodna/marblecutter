#!/usr/bin/env bash

bucket=mapzen-dynamic-tiler-test
source=EU-DEM

set -eo pipefail

find . -type f -name \*_footprint.json | \
  while read footprint; do
    ogr2ogr \
      -select filename \
      --config PG_USE_COPY YES \
      -lco CREATE_TABLE=OFF \
      -lco DROP_TABLE=OFF \
      -f PGDump \
      -nln footprints \
      -nlt PROMOTE_TO_MULTI \
      /vsistdout/ $footprint

    meta=$(jq .meta ${footprint/_footprint/})
    resolution=$(jq -r .resolution <<< $meta)
    filename=$(basename ${footprint%_footprint.json}.tif)
    echo "UPDATE footprints SET resolution=${resolution}, source='${source}', url='s3://${bucket}/${source}/0/${filename}', approximate_zoom=least(22, ceil(log(2.0, ((2 * pi() * 6378137) / (${resolution} * 256))::numeric))) WHERE filename='${filename}';"
    echo "UPDATE footprints SET min_zoom=approximate_zoom - 3, max_zoom=approximate_zoom WHERE filename='${filename}';"
    # 120 is the number of pixels to buffer; it's the sample value for rio footprint + 20%
    echo "UPDATE footprints SET wkb_geometry=ST_Multi(ST_Buffer(wkb_geometry::geography, resolution * 120)::geometry)"
  done | psql -q
