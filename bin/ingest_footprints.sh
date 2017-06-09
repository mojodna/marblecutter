#!/usr/bin/env bash

bucket=elevation-sources-transcoded

set -eo pipefail

aws s3 ls --recursive s3://$bucket | \
grep _footprint.json | \
awk '{ print $4 }' | \
while read footprint_key; do
  ingest_single_footprint.sh s3://$bucket/$footprint_key
done
