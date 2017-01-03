FROM ubuntu:16.04
MAINTAINER Seth Fitzsimmons <seth@mojodna.net>

ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update && \
  apt-get install -y --no-install-recommends software-properties-common && \
  add-apt-repository ppa:ubuntugis/ppa && \
  apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    gdal-bin \
    jq \
    libgdal-dev \
    python-dev \
    python-pip \
    python-setuptools \
    python-wheel && \
  apt-get clean

COPY requirements.txt /app/requirements.txt

WORKDIR /app

RUN pip install -U numpy && \
  pip install -Ur requirements.txt && \
  pip install -U awscli gevent gunicorn && \
  rm -rf /root/.cache

# override this accordingly; should be 2-4x $(nproc)
ENV WEB_CONCURRENCY 4
ENV CPL_TMPDIR /tmp
ENV CPL_VSIL_CURL_ALLOWED_EXTENSIONS .vrt,.tif,.ovr,.msk
ENV GDAL_DISABLE_READDIR_ON_OPEN TRUE
ENV VSI_CACHE TRUE
ENV VSI_CACHE_SIZE 536870912
EXPOSE 8000

COPY . /app

# USER nobody

# ENTRYPOINT ["gunicorn", "-k", "gevent", "-b", "0.0.0.0", "--access-logfile", "-", "app:app"]
