# Zabbix Dashboard

![Python](https://img.shields.io/badge/Python-3.12-blue) ![Flask](https://img.shields.io/badge/Flask-3.x-black) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-blue) ![Docker](https://img.shields.io/badge/Docker-Compose-blue) ![Status](https://img.shields.io/badge/status-beta-orange)

Dashboard web modular para monitoramento de infraestrutura via **API JSON-RPC nativa do Zabbix** com token Bearer, inventário de itens, histórico de 1 a 365 dias e PostgreSQL. Sem OAuth.

## Início rápido

```bash
git clone git@github.com:llongaray/Zabbix-dashboard.git
cd Zabbix-dashboard
cp .env.example .env
# Configure POSTGRES_PASSWORD, ADMIN_PASSWORD, FLASK_SECRET_KEY e FERNET_KEY
docker compose up -d --build
```

Abra **http://localhost:5000**. A configuração do Zabbix pode ser salva na interface; o token é criptografado no PostgreSQL. Gere `FERNET_KEY` com `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` após instalar `cryptography` ou em um ambiente Python com a dependência.

## Arquitetura

- `main.py`: único orquestrador Python na raiz.
- `app/__init__.py`: application factory.
- `app/db.py`: pool SQLAlchemy/PostgreSQL e persistência.
- `app/security.py`: criptografia Fernet.
- `app/services/zabbix.py`: cliente JSON-RPC, descoberta e histórico.
- `app/services/mailing.py`: serviço SMTP STARTTLS preparado para integração.
- `app/routes/__init__.py`: rotas Flask e autenticação.
- `app/templates/`: interface web.

## Segurança e limitações

**Não envie `.env`, credenciais, tokens ou dados reais da infraestrutura para este repositório público.** A chave Fernet deve permanecer fora do banco e do Git. O dashboard vincula-se somente a `127.0.0.1`. A autenticação administrativa é simples e requer endurecimento antes de exposição em rede. O módulo SMTP está preparado, mas a tela de configuração e o agendamento automático de relatórios ainda não estão integrados nesta revisão. GPU e inventário dependem dos itens monitorados no Zabbix. Dados históricos dependem da retenção. A interface consulta o backend sob demanda; WebSocket e alertas agendados estão planejados para a próxima revisão.

## Desenvolvimento

Separação por responsabilidade, funções reutilizáveis, pool de conexões limitado e chamadas de API com timeout. Testes de integração Docker/Zabbix devem ser realizados antes de release estável.

## Licença

GPL-3.0 — consulte [LICENSE](LICENSE).
