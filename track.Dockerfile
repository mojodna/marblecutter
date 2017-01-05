FROM lambci/lambda:build-python2.7

# NOTE: comment deps/ in .dockerignore for this to work
ADD deps/automake16-1.6.3-18.6.amzn1.noarch.rpm /tmp
ADD deps/libcurl-devel-7.40.0-8.54.amzn1.x86_64.rpm /tmp
ADD deps/libjpeg-turbo-devel-1.2.90-5.14.amzn1.x86_64.rpm /tmp
ADD deps/libpng-devel-1.2.49-2.14.amzn1.x86_64.rpm /tmp

RUN \
  rpm -ivh /tmp/automake16-1.6.3-18.6.amzn1.noarch.rpm \
    /tmp/libcurl-devel-7.40.0-8.54.amzn1.x86_64.rpm \
    /tmp/libjpeg-turbo-devel-1.2.90-5.14.amzn1.x86_64.rpm \
    /tmp/libpng-devel-1.2.49-2.14.amzn1.x86_64.rpm

# Fetch PROJ.4

RUN \
  curl -L http://download.osgeo.org/proj/proj-4.9.3.tar.gz | tar zxf - -C /tmp

# Build and install PROJ.4

WORKDIR /tmp/proj-4.9.3

RUN \
  ./configure \
    --prefix=/var/task && \
  make -j $(nproc) && \
  make install

# Fetch GDAL

RUN \
  curl -L http://download.osgeo.org/gdal/2.1.2/gdal-2.1.2.tar.gz | tar zxf - -C /tmp

# Build + install GDAL

WORKDIR /tmp/gdal-2.1.2

RUN \
  ./configure \
    --prefix=/var/task \
    --datarootdir=/var/task/share/gdal \
    --without-qhull \
    --without-mrf \
    --without-grib \
    --without-pcraster \
    --without-png \
    --without-gif \
    --without-pcidsk && \
  make -j $(nproc) && \
  make install

# Install Python deps in a virtualenv
RUN \
  virtualenv /tmp/virtualenv

ENV PATH /tmp/virtualenv/bin:/var/task/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN \
  pip install -U cachetools flask flask_cors jinja2 mercantile numpy pillow raven requests werkzeug && \
  pip install -U --no-binary :all: rasterio

WORKDIR /var/task

COPY . /var/task

# touch start
# python app.py
# # load stuff
# find /tmp/virtualenv/lib/python2.7/site-packages -type f -anewer start
