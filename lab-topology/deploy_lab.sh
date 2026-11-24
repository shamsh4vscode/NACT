#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
./generate_configs.sh
CONTAINERLAB="${CONTAINERLAB:-$HOME/.local/bin/containerlab}"
if [ ! -x "$CONTAINERLAB" ]; then CONTAINERLAB=containerlab; fi

KEY_DIR=.secrets
mkdir -p "$KEY_DIR"
if [ ! -s "$KEY_DIR/id_ed25519" ]; then
  ssh-keygen -t ed25519 -N "" -f "$KEY_DIR/id_ed25519" -C nact-lab
fi
cp "$KEY_DIR/id_ed25519.pub" configs/authorized_keys
chmod 600 "$KEY_DIR/id_ed25519"
chmod 644 configs/authorized_keys
: > "$KEY_DIR/known_hosts"

docker build -t nact/frr-ssh:latest -f Dockerfile .

"$CONTAINERLAB" deploy -t enterprise-12node.clab.yml --reconfigure
for address in 172.20.20.11 172.20.20.12 172.20.20.13 172.20.20.14 172.20.20.15 172.20.20.16 172.20.20.17 172.20.20.18 172.20.20.19 172.20.20.20; do
  found_key=false
  for attempt in $(seq 1 30); do
    if ssh-keyscan -H -T 2 "$address" >> "$KEY_DIR/known_hosts" 2>/dev/null; then
      found_key=true
      break
    fi
    sleep 1
  done
  if [ "$found_key" != true ]; then
    echo "Could not read the SSH host key for $address" >&2
    exit 1
  fi
done
chmod 600 "$KEY_DIR/known_hosts"
docker ps --format '{{.Names}}\t{{.Status}}' | sort
