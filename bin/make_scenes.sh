#!/usr/bin/env bash

bucket="oin-hotosm"

for upload in $(aws s3 ls s3://${bucket}/ | awk '{print $2}'); do
  echo "Upload ${upload}"
  for scene in $(aws s3 ls s3://${bucket}/$upload | awk '{print $2}'); do
    echo "Scene ${scene}"
    aws s3 ls s3://${bucket}/${upload}${scene} | \
      grep json | \
      grep -v footprint | \
      grep -v scene | \
      grep -v meta | \
      awk "{print \"http://${bucket}.s3.amazonaws.com/${upload}${scene}\" \$4 }" | \
      xargs bin/make_a_scene.js | \
      aws s3 cp - s3://${bucket}/${upload}${scene}scene.json --acl public-read
  done
done
