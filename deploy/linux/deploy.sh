#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."

exec 9>.zabbix-deploy.lock
flock -n 9 || { echo 'Já existe um deploy em andamento neste checkout.' >&2; exit 1; }
compose=(bash deploy/linux/compose.sh)
"${compose[@]}" config --quiet
"${compose[@]}" up -d --build --wait --wait-timeout 90
binding=$("${compose[@]}" port dashboard 5000)
if [[ "$binding" != 127.0.0.1:* ]]; then
  echo "Publicação local inesperada: $binding" >&2
  exit 1
fi
curl --fail --silent --show-error --output /dev/null --max-time 8 \
  --retry 10 --retry-connrefused --retry-delay 1 "http://$binding/login"
"${compose[@]}" ps
printf 'Dashboard disponível em http://%s/\n' "$binding"
