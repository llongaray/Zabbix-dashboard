#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."

usage() { echo 'Uso: bash deploy/linux/update.sh [--apply [--deploy]]'; }
apply=0
deploy=0
for arg in "$@"; do
  case "$arg" in
    --apply) apply=1 ;;
    --deploy) deploy=1 ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done
if ((deploy && !apply)); then usage >&2; exit 2; fi
if ((deploy)) && [[ ! -f .env ]]; then
  echo 'Execute deploy/linux/install.sh antes de usar --deploy.' >&2
  exit 1
fi
branch=$(git symbolic-ref --quiet --short HEAD)
exec 8>"$(git rev-parse --git-path zabbix-update.lock)"
flock -n 8 || { echo 'Já existe uma atualização deste checkout em andamento.' >&2; exit 1; }
if ((apply)) && [[ -n "$(git status --porcelain)" ]]; then
  echo 'Há alterações locais. Revise o git status antes de atualizar.' >&2
  exit 1
fi
remote="refs/remotes/origin/$branch"
git fetch --no-tags origin "refs/heads/$branch:$remote"
git merge-base --is-ancestor HEAD "$remote" ||
  { echo "O checkout divergiu de origin/$branch. Revise antes de atualizar." >&2; exit 1; }
git --no-pager log --oneline "HEAD..$remote"
if ((apply)); then
  git merge --ff-only "$remote"
fi
if ((deploy)); then
  bash deploy/linux/deploy.sh
fi
