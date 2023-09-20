#!/bin/sh
service ssh start
bash /root/.bashrc
cp /root/authorized_keys /root/.ssh/authorized_keys
chown root:root /root/.ssh/authorized_keys
exec "$@"
