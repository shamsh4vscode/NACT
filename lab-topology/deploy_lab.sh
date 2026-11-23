#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
./generate_configs.sh
CONTAINERLAB="${CONTAINERLAB:-$HOME/.local/bin/containerlab}"
if [ ! -x "$CONTAINERLAB" ]; then CONTAINERLAB=containerlab; fi

LAB_KIND=linux
if docker image inspect ceos:latest >/dev/null 2>&1 || docker image inspect arista/ceos:latest >/dev/null 2>&1; then
  LAB_KIND=ceos
fi

cat > /tmp/nact-clab-kind.txt <<EOF
$LAB_KIND
EOF
echo "Selected lab kind: $LAB_KIND"

"$CONTAINERLAB" deploy -t enterprise-12node.clab.yml --reconfigure
docker ps --format '{{.Names}}\t{{.Status}}' | sort
