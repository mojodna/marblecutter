footprint_uri=$1

if [[ -z "$footprint_uri" ]]; then
  >&2 echo "usage: $(basename $0) <source image footprint s3 uri>"
  exit 1
fi

set -e

>&2 echo "Ingesting footprint for ${footprint_uri}"

# We're going to say the source is the root of the S3 key after the bucket name
source=$(awk -F '/' '{print $4}' <<< $footprint_uri)

# Read the metadata to pull out useful info and get the footprint URI
meta=$(aws s3 cp ${footprint_uri/_footprint.json/.json} - | jq .meta)
resolution=$(jq -r .resolution <<< $meta)
footprint_uri=$(jq -r .footprint <<< $meta)
transcoded_uri=${footprint_uri/_footprint.json/.tif}
filename=$(basename $transcoded_uri)

# Since the following is not an idempotent process,
# delete any rows for this filename if they exist already.
cat << EOF
  DELETE FROM footprints WHERE filename='${filename}';
EOF

# Read the footprint GeoJSON and use ogr2ogr to convert to pgdump format
aws s3 cp $footprint_uri - | \
ogr2ogr \
  -select filename \
  --config PG_USE_COPY YES \
  -lco CREATE_TABLE=OFF \
  -lco DROP_TABLE=OFF \
  -f PGDump \
  -nln footprints \
  -nlt PROMOTE_TO_MULTI \
  /vsistdout/ /vsistdin/

# Update the data we just added to include info about resolution, etc.
cat << EOF
  UPDATE footprints SET
    resolution=${resolution},
    approximate_zoom=least(22, ceil(log(2.0, ((2 * pi() * 6378137) / (${resolution} * 256))::numeric)))
  WHERE filename='${filename}';
  UPDATE footprints SET
    min_zoom=greatest(0, approximate_zoom - 4),
    max_zoom=20,
    source='${source}',
    url='${transcoded_uri}'
  WHERE filename='${filename}';
EOF
