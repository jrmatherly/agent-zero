#!/bin/bash
set -e

# Set up SSH (CD-C3: disable root login, allow only appuser)
mkdir -p /var/run/sshd && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config && \
    echo "AllowUsers appuser" >> /etc/ssh/sshd_config
