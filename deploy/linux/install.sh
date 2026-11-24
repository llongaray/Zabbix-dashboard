#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."

for dependency in docker openssl curl flock; do
  command -v "$dependency" >/dev/null || { echo "Dependência ausente: $dependency" >&2; exit 1; }
done
docker compose version >/dev/null
docker info >/dev/null
if [[ ! -e .env ]]; then
  umask 077
  config=$(mktemp .env.install.XXXXXX)
  trap 'rm -f -- "$config"' EXIT
  postgres=$(openssl rand -hex 24)
  admin=$(openssl rand -hex 18)
  flask=$(openssl rand -hex 32)
  fernet=$(openssl rand -base64 32 | tr '+/' '-_')
  sed -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$postgres/" \
      -e "s/^ADMIN_PASSWORD=.*/ADMIN_PASSWORD=$admin/" \
      -e "s/^FLASK_SECRET_KEY=.*/FLASK_SECRET_KEY=$flask/" \
      -e "s/^FERNET_KEY=.*/FERNET_KEY=$fernet/" \
      -e 's|^SMTP_MICROSOFT_REDIRECT_URI=.*|SMTP_MICROSOFT_REDIRECT_URI=http://localhost:18081/smtp/microsoft/callback|' \
      .env.example > "$config"
  printf '\nZABBIX_HTTP_PORT=18081\n' >> "$config"
  ln -- "$config" .env
  echo '.env criado com credenciais novas. Consulte o arquivo local para obter a senha administrativa.'
else
  echo 'O .env existente será usado.'
fi
bash deploy/linux/deploy.sh
