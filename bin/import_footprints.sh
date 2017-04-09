#!/usr/bin/env bash

set -eo pipefail

find . -name *_footprint.json |
  while read geojson; do
    echo $geojson
    ogr2ogr \
      -select "id, filename" \
      --config PG_USE_COPY YES \
      -lco CREATE_TABLE=OFF \
      -lco DROP_TABLE=OFF \
      -f PGDump \
      -nln footprints \
      -nlt PROMOTE_TO_MULTI \
      /vsistdout/ $geojson | psql -d mapzen
  done
