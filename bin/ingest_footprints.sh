#!/usr/bin/env bash

bucket=elevation-sources-transcoded

set -eo pipefail

aws s3 ls --recursive s3://$bucket | \
grep _footprint.json | \
head -n 1 | \
awk '{ print $4 }' | \
while read footprint_key; do
  # We're going to say the source is the root of the S3 key
  source=$(awk -F '/' '{print $1}' <<< $footprint_key)

  # Read the footprint and use ogr2ogr to convert to pgdump format
  aws s3 cp s3://$bucket/$footprint_key - | \
  ogr2ogr \
    -select filename \
    --config PG_USE_COPY YES \
    -lco CREATE_TABLE=OFF \
    -lco DROP_TABLE=OFF \
    -f PGDump \
    -nln footprints \
    -nlt PROMOTE_TO_MULTI \
    /vsistdout/ /vsistdin/

  # Read the tilejson metadata for the rest
  metadata_key=${footprint_key/_footprint}
  meta=$(aws s3 cp s3://$bucket/$metadata_key - | jq .meta)
  resolution=$(jq -r .resolution <<< $meta)
  transcoded_key=${footprint_key/_footprint.json/.tif}
  filename=$(basename $transcoded_key)

  # Update the data we just added to include info about resolution, etc.
  # ... 120 is the number of pixels to buffer; it's the sample value for rio footprint + 20%
  cat << EOF
    UPDATE footprints SET
      resolution=${resolution},
      approximate_zoom=least(22, ceil(log(2.0, ((2 * pi() * 6378137) / (${resolution} * 256))::numeric)))
    WHERE filename='${filename}';
    UPDATE footprints SET
      min_zoom=approximate_zoom - 3,
      max_zoom=approximate_zoom,
      source='${source}',
      url='s3://${bucket}/${transcoded_key}',
      wkb_geometry=ST_Multi(ST_Buffer(wkb_geometry::geography, resolution * 120)::geometry)
    WHERE filename='${filename}';
EOF

done
