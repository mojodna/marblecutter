#!/usr/bin/env bash

curl http://172.16.142.145:8000/geotiff/10/164/400.tif > /dev/null
curl http://172.16.142.145:8000/normal/10/164/398@2x.png > /dev/null
curl http://172.16.142.145:8000/normal/10/164/398.png > /dev/null
curl http://172.16.142.145:8000/terrarium/10/164/398@2x.png > /dev/null
curl http://172.16.142.145:8000/terrarium/10/164/398.png > /dev/null
curl http://172.16.142.145:8000/hillshade/10/164/398@2x.png > /dev/null
curl http://172.16.142.145:8000/hillshade/10/164/398.png > /dev/null
curl http://172.16.142.145:8000/hillshade/ > /dev/null
curl http://172.16.142.145:8000/normal/preview > /dev/null
curl http://172.16.142.145:8000/static/images/transparent.png > /dev/null
