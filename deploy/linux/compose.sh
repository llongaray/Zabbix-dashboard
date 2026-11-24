#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."

[[ -f .env ]] || { echo 'Execute deploy/linux/install.sh para criar o .env.' >&2; exit 1; }
docker compose version >/dev/null
exec docker compose --project-name zabbix-dashboard --env-file .env \
  -f compose.yaml -f deploy/docker/compose.linux.yml "$@"
