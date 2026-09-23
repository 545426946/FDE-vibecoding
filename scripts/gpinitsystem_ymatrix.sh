#!/bin/bash
set -eux
IP=$(hostname -i | awk '{print $1}')
if ! grep -q '[[:space:]]mdw$' /etc/hosts; then
  echo "${IP} mdw" >> /etc/hosts
fi
if ! grep -q '127.0.0.1' /etc/hosts; then
  echo "127.0.0.1 localhost" >> /etc/hosts
fi
cat /etc/hosts

su - mxadmin -c "ssh -o StrictHostKeyChecking=no mdw hostname"

mkdir -p /data/master /data/primary
chown -R mxadmin:mxadmin /data

cat > /home/mxadmin/gpinitsystem_config <<'EOF'
ARRAY_NAME="YMatrix Docker Demo"
SEG_PREFIX=gpseg
PORT_BASE=6000
declare -a DATA_DIRECTORY=(/data/primary)
MASTER_HOSTNAME=mdw
MASTER_DIRECTORY=/data/master
MASTER_PORT=5432
TRUSTED_SHELL=ssh
CHECK_POINT_SEGMENTS=8
ENCODING=UNICODE
MACHINE_LIST_FILE=/home/mxadmin/hostfile
EOF
echo mdw > /home/mxadmin/hostfile
chown mxadmin:mxadmin /home/mxadmin/gpinitsystem_config /home/mxadmin/hostfile

su - mxadmin -c "source /usr/local/matrixdb/greenplum_path.sh; gpinitsystem -a -c /home/mxadmin/gpinitsystem_config"
