FROM quay.io/mojodna/gdal22
MAINTAINER Seth Fitzsimmons <seth@mojodna.net>

ENV DEBIAN_FRONTEND noninteractive
ENV PATH=/opt/oam-dynamic-tiler/bin:/opt/oam-dynamic-tiler/node_modules/.bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV CPL_TMPDIR /tmp
ENV CPL_VSIL_CURL_ALLOWED_EXTENSIONS .vrt,.tif,.tiff,.ovr,.msk,.jp2
ENV GDAL_CACHEMAX 512
ENV GDAL_DISABLE_READDIR_ON_OPEN TRUE
ENV VSI_CACHE TRUE
ENV VSI_CACHE_SIZE 536870912

RUN apt-get update \
  && apt-get upgrade -y \
  && apt-get install -y --no-install-recommends \
    apt-transport-https \
    bc \
    build-essential \
    ca-certificates \
    curl \
    cython \
    git \
    jq \
    python-pip \
    python-wheel \
    python-setuptools \
    software-properties-common \
  && curl -sf https://deb.nodesource.com/gpgkey/nodesource.gpg.key | apt-key add - \
  && add-apt-repository -s "deb https://deb.nodesource.com/node_4.x $(lsb_release -c -s) main" \
  && apt-get update \
  && apt-get install --no-install-recommends -y nodejs \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/oam-dynamic-tiler

COPY requirements.txt /opt/oam-dynamic-tiler/requirements.txt

RUN pip install -U numpy && \
  pip install -U --no-binary :all: rasterio>=1.0a6 && \
  pip install -r requirements.txt && \
  pip install -U awscli && \
  rm -rf /root/.cache

COPY package.json /opt/oam-dynamic-tiler/package.json

RUN \
  npm install \
  && rm -rf /root/.npm

COPY . /opt/oam-dynamic-tiler
