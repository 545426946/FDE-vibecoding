#!/bin/bash
set -eu
pgrep -x sshd >/dev/null 2>&1 || { ssh-keygen -A || true; /usr/sbin/sshd; }
/etc/init.d/matrixdb-supervisor start || true
su - mxadmin -c 'source /usr/local/matrixdb/greenplum_path.sh; export MASTER_DATA_DIRECTORY=/data/master/gpseg-1; gpstart -a' || true
su - mxadmin -c 'source /usr/local/matrixdb-4.8.12.community/greenplum_path.sh; export MASTER_DATA_DIRECTORY=/mxdata_20260918034353/master/mxseg-1; gpstart -a' || true
echo "YMatrix started on 5432 (migrate) and 5433 (MatrixUI)"