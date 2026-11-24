# Instalação Linux

Use um checkout próprio em `/opt/zabbix-dashboard`, acessível ao operador do deploy.
Pré-requisitos: Git com acesso SSH ao repositório da Avansat, Docker Engine
com Compose v2 que suporte `up --wait`, OpenSSL, curl e flock. Execute com uma
conta que tenha permissão para usar Docker. Confira se a porta 18081 está livre.

```bash
git clone --branch V2.0 git@github.com:Avansat-Tecnologias/Zabbix-dashboard.git /opt/zabbix-dashboard
cd /opt/zabbix-dashboard
bash deploy/linux/install.sh
```

O instalador gera o `.env` com permissão 0600 e inicia o dashboard, o
coletor e um PostgreSQL próprios. Consulte `ADMIN_PASSWORD` no arquivo
local e cadastre o token de leitura do Zabbix na aba Configurações.
O projeto Compose se chama `zabbix-dashboard` e a porta fica vinculada a
`127.0.0.1`. Para outra porta, defina `ZABBIX_HTTP_PORT` no `.env`.

## Atualizar e operar

```bash
bash deploy/linux/update.sh
bash deploy/linux/update.sh --apply --deploy
bash deploy/linux/deploy.sh
bash deploy/linux/compose.sh ps
bash deploy/linux/compose.sh logs --tail=100 dashboard collector
```

O update usa `origin` e só aceita avanço direto da branch atual. O deploy
recompila o código e verifica a página de login. O PostgreSQL usa um
volume persistente do projeto. Faça backup do banco e do `.env` antes de
uma atualização de produção. A chave Fernet do `.env` é necessária para
recuperar credenciais criptografadas no banco.

## Publicar em HTTPS

Use um virtual host dedicado com o exemplo em
[`deploy/nginx/zabbix-dashboard.conf.example`](../deploy/nginx/zabbix-dashboard.conf.example).
Antes de publicar, defina `SESSION_COOKIE_SECURE=true` no `.env`.
Se for usar SMTP Microsoft com OAuth, configure também
`SMTP_MICROSOFT_REDIRECT_URI` com a URL HTTPS do novo host e registre-a no
Entra. Execute o deploy após editar o `.env`, valide o Nginx com
`nginx -t` e recarregue o serviço. O exemplo usa a raiz do hostname e
encaminha o Socket.IO separadamente.
