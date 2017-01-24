FROM quay.io/hotosm/oam-dynamic-tiler-tools
MAINTAINER Seth Fitzsimmons <seth@mojodna.net>

RUN \
  pip install -U gevent gunicorn && \
  rm -rf /root/.cache

# override this accordingly; should be 2-4x $(nproc)
ENV WEB_CONCURRENCY 4
EXPOSE 8000

USER nobody

ENTRYPOINT ["gunicorn", "-k", "gevent", "-b", "0.0.0.0", "--access-logfile", "-", "app:app"]
