FROM ubuntu:16.04
MAINTAINER Seth Fitzsimmons <seth@mojodna.net>

ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update && \
  apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y --no-install-recommends \
    bc \
    build-essential \
    curl \
    cython \
    jq \
    python-pip \
    python-wheel \
    python-setuptools && \
  apt-get clean

RUN \
  apt install -y --no-install-recommends debhelper dh-autoreconf autotools-dev zlib1g-dev libnetcdf-dev netcdf-bin libjasper-dev libpng-dev libjpeg-dev libgif-dev libwebp-dev libhdf4-alt-dev libhdf5-dev libpcre3-dev libpq-dev libxerces-c-dev unixodbc-dev doxygen d-shlibs libgeos-dev dh-python python-all-dev python-numpy libcurl4-gnutls-dev libsqlite3-dev libogdi3.2-dev chrpath swig patch libexpat1-dev libproj-dev libdap-dev libxml2-dev libspatialite-dev libepsilon-dev libpoppler-private-dev liblzma-dev libopenjp2-7-dev libarmadillo-dev libfreexl-dev libkml-dev liburiparser-dev && \
  mkdir -p /tmp/gdal-dev && \
  curl -L https://github.com/OSGeo/gdal/archive/3288b145e6e966499a961c27636f2c9ea80157c2.tar.gz | tar zxf - -C /tmp/gdal-dev --strip-components=1 && \
  cd /tmp/gdal-dev/gdal && \
  ./configure --prefix=/usr \
			--mandir=/usr/share/man \
			--includedir=/usr/include/gdal \
			--with-threads \
			--with-grass=no \
			--with-hide-internal-symbols=yes \
			--with-rename-internal-libtiff-symbols=yes \
			--with-rename-internal-libgeotiff-symbols=yes \
			--with-libtiff=internal \
			--with-geotiff=internal \
			--with-webp \
			--with-jasper \
			--with-netcdf \
			--with-hdf5=/usr/lib/x86_64-linux-gnu/hdf5/serial \
			--with-xerces \
			--with-geos \
			--with-sqlite3 \
			--with-curl \
			--with-pg \
			--with-python \
			--with-odbc \
			--with-ogdi \
			--with-dods-root=/usr \
			--with-static-proj4=yes \
			--with-spatialite=/usr \
			--with-cfitsio=no \
			--with-ecw=no \
			--with-mrsid=no \
			--with-poppler=yes \
			--with-openjpeg=yes \
			--with-freexl=yes \
			--with-libkml=yes \
			--with-armadillo=yes \
			--with-liblzma=yes \
			--with-epsilon=/usr && \
  make -j $(nproc) && \
  make install && \
  cd / && \
  rm -rf /tmp/gdal-dev && \
  apt-get clean

COPY requirements.txt /app/requirements.txt

WORKDIR /app

RUN pip install -U numpy && \
  pip install -Ur requirements.txt && \
  pip install -U awscli gevent gunicorn && \
  rm -rf /root/.cache

# override this accordingly; should be 2-4x $(nproc)
ENV WEB_CONCURRENCY 4
ENV PATH=/app/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV CPL_TMPDIR /tmp
ENV CPL_VSIL_CURL_ALLOWED_EXTENSIONS .vrt,.tif,.ovr,.msk
ENV GDAL_CACHEMAX 512
ENV GDAL_DISABLE_READDIR_ON_OPEN TRUE
ENV VSI_CACHE TRUE
ENV VSI_CACHE_SIZE 536870912
EXPOSE 8000

COPY . /app

# USER nobody

# ENTRYPOINT ["gunicorn", "-k", "gevent", "-b", "0.0.0.0", "--access-logfile", "-", "app:app"]
