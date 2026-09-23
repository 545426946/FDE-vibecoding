#!/bin/bash
set -eux
HBA=/data/master/gpseg-1/pg_hba.conf
CONF=/data/master/gpseg-1/postgresql.conf

grep -q '0.0.0.0/0' "$HBA" || echo 'host all all 0.0.0.0/0 md5' >> "$HBA"
grep -q '::0/0' "$HBA" || echo 'host all all ::0/0 md5' >> "$HBA"

if grep -q "^listen_addresses" "$CONF"; then
  sed -i "s/^listen_addresses.*/listen_addresses = '*'/" "$CONF"
else
  echo "listen_addresses = '*'" >> "$CONF"
fi
chown mxadmin:mxadmin "$HBA" "$CONF"

if ! grep -q MASTER_DATA_DIRECTORY /home/mxadmin/.bashrc; then
  cat >> /home/mxadmin/.bashrc <<'EOF'
source /usr/local/matrixdb/greenplum_path.sh
export MASTER_DATA_DIRECTORY=/data/master/gpseg-1
EOF
fi

su - mxadmin <<'EOF'
source /usr/local/matrixdb/greenplum_path.sh
export MASTER_DATA_DIRECTORY=/data/master/gpseg-1
gpstop -u
createdb mxadmin || true
psql postgres -c "ALTER USER mxadmin WITH PASSWORD 'changeme';"
psql -d mxadmin -c "SELECT version();"
psql -d mxadmin -c "SELECT * FROM gp_segment_configuration;"
EOF

ss -lntp | grep 5432 || true
tail -20 "$HBA"
