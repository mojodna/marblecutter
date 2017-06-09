footprint_uri=$1

if [[ -z "$footprint_uri" ]]; then
  >&2 echo "usage: $(basename $0) <source image footprint s3 uri>"
  exit 1
fi

set -e

>&2 echo "Ingesting footprint for ${footprint_uri}"

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

# We're going to say the source is the root of the S3 key after the bucket name
source=$(awk -F '/' '{print $4}' <<< $footprint_uri)

# Read the metadata to pull out useful info and get the footprint URI
meta=$(aws s3 cp ${footprint_uri/_footprint.json/.json} - | jq .meta)
resolution=$(jq -r .resolution <<< $meta)
footprint_uri=$(jq -r .footprint <<< $meta)
transcoded_uri=${footprint_uri/_footprint.json/.tif}
filename=$(basename $transcoded_uri)

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
    url='${transcoded_uri}',
    wkb_geometry=ST_Multi(ST_Buffer(wkb_geometry::geography, resolution * 120)::geometry)
  WHERE filename='${filename}';
EOF
