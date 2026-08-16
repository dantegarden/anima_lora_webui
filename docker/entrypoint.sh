#!/bin/bash
set -euo pipefail

mkdir -p /home/ubuntu/datasets
mkdir -p /var/run/sshd

# Set the root password; callers can override it with SSH_PASSWORD.
export SSH_PASSWORD="${SSH_PASSWORD:-bizyair}"
echo "root:$SSH_PASSWORD" | chpasswd
if [ -n "${CODE_SERVER_PASSWORD:-}" ]; then
    PASSWORD="$CODE_SERVER_PASSWORD"
    CODE_SERVER_PASSWORD_SOURCE="CODE_SERVER_PASSWORD"
elif [ -n "${PASSWORD:-}" ]; then
    CODE_SERVER_PASSWORD_SOURCE="PASSWORD"
else
    PASSWORD="$(openssl rand -hex 16)"
    CODE_SERVER_PASSWORD_SOURCE="generated"
fi
export PASSWORD
printf '[entrypoint] code-server password (%s): %s\n' "$CODE_SERVER_PASSWORD_SOURCE" "$PASSWORD"
# Ignore the build-time generated config so code-server uses the runtime password.
rm -f /root/.config/code-server/config.yaml

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

MODEL_DOWNLOAD_SCRIPT="/workspace/anima_lora_webui/scripts/download_models_from_oss.sh"
if [ -x "$MODEL_DOWNLOAD_SCRIPT" ]; then
    echo "[entrypoint] downloading OSS models before starting services..."
    "$MODEL_DOWNLOAD_SCRIPT"
else
    echo "[entrypoint] model download script not found or not executable: $MODEL_DOWNLOAD_SCRIPT" >&2
fi

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/anima_lora.conf
