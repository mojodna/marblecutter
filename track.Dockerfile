FROM lambci/lambda:build-python2.7

RUN \
  yum install -y \
    automake16 \
    libcurl-devel \
    libjpeg-turbo-devel \
    libpng-devel

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
  pip install -U cachetools Cython flask flask_cors jinja2 mercantile numpy pillow raven requests werkzeug && \
  pip install -U --no-binary :all: https://github.com/mojodna/rasterio/archive/1.0a5+nogil.tar.gz && \
  pip install -U rio-color

WORKDIR /var/task

COPY . /var/task

# touch start
# python app.py
# # load stuff
# find /tmp/virtualenv/lib/python2.7/site-packages -type f -anewer start
