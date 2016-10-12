FROM lambci/lambda:build-python2.7

# Install deps

ADD automake16-1.6.3-18.6.amzn1.noarch.rpm /tmp
ADD libcurl-devel-7.40.0-8.54.amzn1.x86_64.rpm /tmp
ADD libpng-devel-1.2.49-2.14.amzn1.x86_64.rpm /tmp

RUN \
  rpm -ivh /tmp/automake16-1.6.3-18.6.amzn1.noarch.rpm \
    /tmp/libcurl-devel-7.40.0-8.54.amzn1.x86_64.rpm \
    /tmp/libpng-devel-1.2.49-2.14.amzn1.x86_64.rpm

# Fetch PROJ.4

RUN \
  curl -L http://download.osgeo.org/proj/proj-4.9.3.tar.gz | tar zxf - -C /tmp

# Build and install PROJ.4

WORKDIR /tmp/proj-4.9.3

RUN \
  ./configure && \
  make -j $(nproc) && \
  make install

# Fetch GDAL

RUN \
  curl -L http://download.osgeo.org/gdal/2.1.1/gdal-2.1.1.tar.gz | tar zxf - -C /tmp

# Build + install GDAL

WORKDIR /tmp/gdal-2.1.1

RUN \
  ./configure \
    --datarootdir=/var/task/share/gdal \
    --without-qhull \
    --without-mrf \
    --without-grib \
    --without-pcraster \
    --without-png \
    --without-jpeg \
    --without-gif \
    --without-pcidsk && \
  make -j $(nproc) && \
  make install

# Install Python deps in a virtualenv

RUN \
  virtualenv /tmp/virtualenv

ENV PATH /tmp/virtualenv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN \
  pip install numpy && \
  pip install -U cachetools mercantile pillow rasterio raven requests

# Add GDAL libs to the function zip

WORKDIR /usr/local

RUN \
  strip lib/libgdal.so.20.1.1 && \
  strip lib/libproj.so.12.0.0

RUN \
  zip --symlinks \
    -r9 /tmp/task.zip \
    lib/libgdal.so* \
    lib/libproj.so*

WORKDIR /var/task

RUN \
  zip --symlinks \
    -r9 /tmp/task.zip \
    share/gdal/ \
    .cache/matplotlib/

# Add Python deps to the function zip

WORKDIR /tmp/virtualenv/lib64/python2.7/site-packages

# skip the zipping (above, too) and put it in a staging directory that can be copied to a volume or output via tar on stdout
RUN \
  zip --symlinks \
    -x easy_install.py\* \
    -x pip\* \
    -x pkg_resources\* \
    -x setuptools\* \
    -x wheel\* \
    -x \*/tests/\* \
    -x \*/test/\* \
    -r9 /tmp/task.zip *
