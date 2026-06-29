#!/bin/bash
set -euo pipefail

mkdir -p /var/run/sshd

# Set the root password; callers can override it with SSH_PASSWORD.
export SSH_PASSWORD="${SSH_PASSWORD:-MSgouUQP4vhET}"
echo "root:$SSH_PASSWORD" | chpasswd

sed -ri 's/^#?PermitRootLogin .*/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -ri 's/^#?PasswordAuthentication .*/PasswordAuthentication yes/' /etc/ssh/sshd_config
sed -ri 's/^UsePAM .*/UsePAM no/' /etc/ssh/sshd_config
grep -qxF 'ClientAliveInterval 300' /etc/ssh/sshd_config || echo 'ClientAliveInterval 300' >> /etc/ssh/sshd_config
grep -qxF 'ClientAliveCountMax 288' /etc/ssh/sshd_config || echo 'ClientAliveCountMax 288' >> /etc/ssh/sshd_config
grep -qxF 'TCPKeepAlive yes' /etc/ssh/sshd_config || echo 'TCPKeepAlive yes' >> /etc/ssh/sshd_config

ssh-keygen -A

if ! grep -q 'Export container environment variables' /root/.bashrc; then
cat >> /root/.bashrc <<'EOF'
# Export container environment variables
OLD=$IFS
IFS=$'\n'
for item in `cat /proc/1/environ | tr '\0' '\n'`
do
    export $item
done
IFS=$OLD
EOF
fi

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/anima_lora.conf
