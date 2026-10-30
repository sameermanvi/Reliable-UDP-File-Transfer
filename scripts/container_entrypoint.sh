#!/bin/sh
set -eu
mkdir -p /var/run/openvswitch /var/log/openvswitch /etc/openvswitch
if [ ! -e /etc/openvswitch/conf.db ]; then
    ovsdb-tool create /etc/openvswitch/conf.db /usr/share/openvswitch/vswitch.ovsschema
fi
ovsdb-server /etc/openvswitch/conf.db --remote=punix:/var/run/openvswitch/db.sock \
    --pidfile --detach --log-file
ovs-vsctl --no-wait init
ovs-vswitchd --pidfile --detach --log-file
exec "$@"
