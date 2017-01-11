FROM mojodna/oam-dynamic-tiler
MAINTAINER Seth Fitzsimmons <seth@mojodna.net>

ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update && \
  apt-get upgrade -y && \
  apt-get install -y --no-install-recommends \
    nfs-common && \
  apt-get clean

RUN \
  mkdir -p /efs

ENV CPL_TMPDIR /efs
ENV TMPDIR /efs

# prepend a hashbang and mount command to the entrypoint
# (yes, this is a nasty hack, but it means that the image can be used as a command w/ args)
RUN \
  echo "#!/usr/bin/env bash\nmount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2 \${EFS_HOST}:/ /efs\n$(cat $(which process.sh))" > $(which process.sh)

ENTRYPOINT ["process.sh"]
