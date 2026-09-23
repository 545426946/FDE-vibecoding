#!/bin/bash
set -eux
ssh-keygen -A || true
pgrep -x sshd >/dev/null 2>&1 || /usr/sbin/sshd

if ! id mxadmin >/dev/null 2>&1; then
  useradd -m -s /bin/bash mxadmin
  echo 'mxadmin:changeme' | chpasswd
fi

mkdir -p /home/mxadmin/.ssh
if [ ! -f /home/mxadmin/.ssh/id_rsa ]; then
  ssh-keygen -t rsa -N '' -f /home/mxadmin/.ssh/id_rsa
fi
cat /home/mxadmin/.ssh/id_rsa.pub >> /home/mxadmin/.ssh/authorized_keys
chmod 700 /home/mxadmin/.ssh
chmod 600 /home/mxadmin/.ssh/authorized_keys /home/mxadmin/.ssh/id_rsa
cat > /home/mxadmin/.ssh/config <<'EOF'
Host *
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
EOF
chown -R mxadmin:mxadmin /home/mxadmin/.ssh

sed -i 's/^[[:space:]]*Password.*/  Password = "changeme"/' /etc/matrixdb/auth.conf || true
echo '---- auth.conf ----'
cat /etc/matrixdb/auth.conf

# mxctl often needs passwordless sudo
if ! grep -q '^mxadmin' /etc/sudoers /etc/sudoers.d/* 2>/dev/null; then
  echo 'mxadmin ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/mxadmin
  chmod 440 /etc/sudoers.d/mxadmin
fi

source /usr/local/matrixdb/greenplum_path.sh
export HOME=/home/mxadmin
mxctl setup collect | mxctl setup plan | mxctl setup exec
