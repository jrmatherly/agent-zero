#!/bin/bash

echo "⚙️  Initializing container..."

# branch from parameter
if [ -z "$1" ]; then
    echo "Error: Branch parameter is empty. Please provide a valid branch name."
    exit 1
fi
BRANCH="$1"

# Copy all contents from persistent /per to root directory (/) without overwriting
cp -r --no-preserve=ownership,mode /per/* /

# allow execution of /root/.bashrc and /root/.profile
chmod 444 /root/.bashrc
chmod 444 /root/.profile

# Fix ownership on mounted volumes and runtime directories so appuser can write.
# Docker volumes created by earlier (root-based) runs may be root-owned;
# /a0/tmp may also be root-owned from the build stage.
chown -R appuser:appuser /a0/usr /a0/tmp 2>/dev/null || true
# Ensure appuser's home directory data dirs exist for fastmcp/platformdirs
mkdir -p /home/appuser/.local/share
chown -R appuser:appuser /home/appuser/.local

# Set root SSH password (requires root; done here instead of prepare.py)
if [ -f /a0/usr/.env ]; then
    ROOT_PASS=$(grep -E '^ROOT_PASSWORD=' /a0/usr/.env 2>/dev/null | cut -d= -f2-)
fi
if [ -z "$ROOT_PASS" ]; then
    ROOT_PASS=$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | head -c 32)
fi
echo "root:${ROOT_PASS}" | chpasswd 2>/dev/null && \
    echo "   ├─ Root password  configured" || \
    echo "   ├─ Root password  skipped (chpasswd unavailable)"

# update package list to save time later
apt-get update > /dev/null 2>&1 &

# let supervisord handle the services
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
