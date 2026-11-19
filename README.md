# Avansat | Zabbix Dashboard

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-29313a?logo=flask)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-316192?logo=postgresql&logoColor=white)
![Socket.IO](https://img.shields.io/badge/Socket.IO-Realtime-6C38B9)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![Status](https://img.shields.io/badge/status-beta-orange)
[![Quality checks](https://github.com/Avansat-Tecnologias/Zabbix-dashboard/actions/workflows/ci.yml/badge.svg)](https://github.com/Avansat-Tecnologias/Zabbix-dashboard/actions/workflows/ci.yml)

> **Avansat Tecnologias | Monitoramento de Infraestrutura**
>
> Plataforma corporativa para centralização de métricas, análise de desempenho,
> histórico operacional, planejamento de capacidade e alertas dos servidores
> monitorados pelo Zabbix.
>
> **Organização:** Avansat-Tecnologias
> **Repositório:** Zabbix-dashboard
> **Tecnologias:** Python, Flask, PostgreSQL 17, Socket.IO e Docker
> **Ambiente:** Windows Server e Linux
> **Status:** Beta — homologação necessária antes da produção
Dashboard web de infraestrutura em **Python, Flask, PostgreSQL 17 e Socket.IO**. Consulta a API oficial JSON-RPC do Zabbix para descobrir hosts, itens, incidentes e histórico de recursos. A interface tem menu lateral, KPIs, tabelas, gráficos e configuração dinâmica do API Token.

> **Beta:** o código e os testes automatizados estão no repositório. A compatibilidade com a infraestrutura corporativa e os templates reais do Zabbix deve ser homologada antes de uso de produção.

## Principais recursos

- **Somente API Token:** não solicita usuário/senha do Zabbix nem depende de OAuth ou MCP.
- **Token protegido:** validado por `host.get` e persistido **criptografado com Fernet** no PostgreSQL; nunca é retornado ao navegador.
- **Configuração sem reload:** salvar ou testar um token atualiza a interface sem recarregar a página.
- **Coletor independente:** container `collector` consulta o Zabbix sem depender de login, navegação ou conexão WebSocket.
- **Cache quente PostgreSQL:** snapshots de hosts/itens e amostras recentes são servidos imediatamente após o login e sobrevivem a reinicializações.
- **Atualização incremental:** o Socket.IO distribui somente mudanças do PostgreSQL, sem realizar consultas ao Zabbix na abertura da página.
- **Descoberta dinâmica:** o coletor consulta os hosts visíveis ao token. A lista do painel inclui os que têm pelo menos uma leitura válida de infraestrutura.
- **Visão geral:** cartões selecionáveis em uma faixa horizontal exibem SO, CPU, RAM, capacidade do volume monitorado e status. A seleção atualiza os indicadores de uso abaixo.
- **Identidade visual:** login e dashboard usam tokens, componentes e ícones do SIGA DS. Consulte [FONTES.md](FONTES.md).
- **Indicadores de recursos:** CPU, memória, disco e rede RX/TX.
- **Histórico dedicado:** gráficos de CPU, RAM, disco e rede RX/TX. O histórico oficial vem de `history.get` (24h) e `trend.get` (7, 30, 90 e 365 dias). O gráfico de disco usa o mesmo item do volume mostrado no painel. CPU, RAM e rede também têm prévia do cache local.
- **Limiares de utilização:** 80% (atenção), 90% (crítico) e 100% (máximo) em CPU, RAM e disco. Na rede, os limites dependem da capacidade da interface.
- **Capacidade:** análise de máximos horários de RAM para estimar folga e sugerir remanejamento entre servidores.
- **Alertas por e-mail:** remetentes SMTP, destinatários e grupos com escopo por servidor.
- **Diagnóstico dos N/D:** explica itens ausentes, valores inválidos e limitações dos templates.
- **Catálogo de API:** métodos oficiais de leitura com diagnóstico opcional de permissão e latência.
- **Diagnósticos:** erros da API Zabbix não invalidam a sessão Flask e não provocam logout automático.

## Como funciona a autenticação?

O Zabbix 7.0 aceita um API Token existente criado pelo frontend ou pela API. As chamadas ao endpoint `/api_jsonrpc.php` usam o cabeçalho `Authorization: Bearer <token>`. Não são necessárias credenciais `username`/`password` para usar um API Token; `user.login` é um método alternativo.

A senha **ADMIN_PASSWORD** é **da aplicação Flask**, independente do token do Zabbix.

Documentação: [Zabbix 7.0 — API](https://www.zabbix.com/documentation/7.0/en/manual/api).

## Instalação Windows + Docker Desktop

### 1. Clonar e configurar variáveis de implantação

```powershell
git clone git@github.com:Avansat-Tecnologias/Zabbix-dashboard.git
cd Zabbix-dashboard
Copy-Item .env.example .env
notepad .env
```

Defina no `.env`:
- `POSTGRES_PASSWORD`: senha forte para o banco.
- `ADMIN_PASSWORD`: senha administrativa para a tela de login.
- `FLASK_SECRET_KEY`: chave longa de sessão.
- `FERNET_KEY`: chave Fernet de criptografia (não a altere sem migrar os tokens).
- `ZABBIX_URL`: endereço do frontend Zabbix. O exemplo da Avansat já está indicado; pode ser substituído no deployment.

Gerar uma chave de sessão:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Gerar a chave Fernet (se não tiver `cryptography` no Python local, instale-a primeiro):

```powershell
python -m pip install cryptography
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Não é necessário colocar `ZABBIX_API_TOKEN` no `.env`.** Ele permanece apenas como fallback opcional. A URL de exemplo antiga `zabbix.example.com` não deve ser utilizada; o backend desta versão trata o antigo placeholder usando a URL padrão documentada.

### 2. Iniciar

```powershell
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 collector dashboard
```

Abra **http://localhost:5000** (publicação local via `127.0.0.1`).

### 3. Cadastrar o token

1. Entre com a senha `ADMIN_PASSWORD` configurada para o Flask.
2. Acesse **Configurações**.
3. Cole **somente o API Token do Zabbix** e clique em **Validar e salvar token**.
4. O backend valida `host.get` antes de substituir qualquer token existente; se a validação falhar, o anterior é preservado.
5. Após a confirmação, as áreas de KPIs, servidores, problemas e histórico serão preenchidas conforme as permissões e os dados realmente disponíveis.

O endereço do endpoint é somente leitura na interface, pois pertence à configuração de implantação. O cache antigo é invalidado ao trocar de token, evitando persistir dados de permissões anteriores.

## Inventário e status dos servidores

- **Sistema operacional e arquitetura** vêm dos itens do agente, com fallback para o inventário do host. Windows e Linux têm ícones próprios.
- **CPUs lógicas** vêm de `system.cpu.num` no Linux e de `Win32_ComputerSystem.NumberOfLogicalProcessors` via WMI no Windows.
- **Modelo da CPU** é exibido quando o Zabbix coleta `system.hw.cpu[0,model]` no Linux ou `wmi.get[root/cimv2,"Select Name from Win32_Processor"]` no Windows.
- **RAM total** vem de `vm.memory.size[total]`. A capacidade do disco corresponde ao volume usado pelo indicador de ocupação. Os valores são exibidos em GiB.
- **Online** e **Sem resposta ao ping** dependem de uma leitura recente de `icmpping`. Quando o ping não está disponível, o status indica a atualidade das métricas coletadas. **Desabilitado** corresponde ao estado de configuração do host no Zabbix.

## Planejamento de capacidade de RAM

A aba **Capacidade** consulta os máximos horários dos últimos 30 dias. As sugestões
exigem ao menos 90% de cobertura e confirmação da RAM total no histórico. O cálculo
estima quanto o doador pode liberar mantendo seu pico projetado em até 70% e pelo
menos 4 GiB de RAM. Candidatos a receber memória atingem 90% ou mais, com meta de
reduzir o pico projetado para até 80%. A mesma folga não é usada em mais de uma sugestão.

Por exemplo, um servidor de 32 GiB com pico de 12 GiB pode liberar até 14 GiB
segundo esses critérios. O painel apresenta a sugestão para análise. Verifique se
as VMs compartilham recursos ou se os módulos físicos são compatíveis antes de executar a mudança.

## Arquitetura

```text
Zabbix-dashboard/
├── main.py                   # Único orquestrador Python na raiz
├── app/
│   ├── __init__.py           # Application factory
│   ├── db.py                 # PostgreSQL e pool SQLAlchemy
│   ├── security.py           # Fernet para credenciais
│   ├── realtime.py           # Distribuidor de cache PostgreSQL via Socket.IO
│   ├── worker.py             # Coletor independente da interface
│   ├── routes/
│   │   ├── __init__.py       # Registro de blueprints e erros
│   │   ├── decorators.py     # Sessão e origem de requisição
│   │   ├── auth.py           # Login administrativo
│   │   ├── settings.py       # Token, conexão e métodos API
│   │   ├── monitoring.py     # Hosts, itens, capacidade e mini-histórico
│   │   ├── smtp.py           # Remetentes, destinatários e grupos de alerta
│   │   └── history.py        # Histórico oficial por recurso
│   ├── services/
│   │   ├── zabbix.py         # Cliente JSON-RPC e validação
│   │   ├── catalog.py        # Métodos de leitura suportados
│   │   ├── monitoring.py     # KPIs, métricas e diagnósticos
│   │   ├── cache.py          # Snapshots e mini-histórico PostgreSQL
│   │   ├── history_series.py # Históricos e normalização das séries
│   │   ├── host_specs.py     # Especificações, volume e status dos hosts
│   │   ├── capacity.py      # Picos de memória e estimativas de remanejamento
│   │   ├── alerts.py        # Roteamento e registro de tentativas de envio
│   │   └── mailing.py       # Envio SMTP por STARTTLS
│   ├── static/
│   │   ├── css/              # Login e dashboard
│   │   └── js/               # Módulos: API, estado, hosts, gráficos, settings, socket
│   └── templates/
├── tests/
├── compose.yaml
├── Dockerfile
├── requirements.txt
└── .env.example
```

### Topologia de eventos

```text
Zabbix --JSON-RPC--> worker Python (container collector, independente)
                             |
                             | snapshots + mini-histórico 72h
                             v
                         PostgreSQL 17
                             |
          Flask (leitura imediata; sem consultar Zabbix no login)
                             |
                   Socket.IO / WebSocket
                             v
                     Dashboard no navegador

Histórico: navegador --> Flask /api/history/series/...
                     --> Zabbix history.get / trend.get
                     --> 4 gráficos separados

POST /api/config --> valida host.get --> criptografa token Fernet
                 --> PostgreSQL (prioridade sobre .env)
```

**O Zabbix não fornece WebSocket neste fluxo:** WebSocket é a camada entre Flask e navegador, alimentada por consultas periódicas à API. Portanto, não é telemetria instantânea nativa; a frequência real depende dos itens monitorados.

O serviço `dashboard` usa 1 worker Gunicorn `gthread`; o serviço `collector` é um processo separado com consultas em lotes de até `HOSTS_PER_CYCLE` hosts. O PostgreSQL mantém os últimos snapshots e mini-histórico local por `CACHE_RETENTION_HOURS` (padrão 72h). Dados históricos de até 365 dias são consultados do Zabbix, respeitando sua retenção.

## Métodos da API

| Método | Uso |
| --- | --- |
| `apiinfo.version` | Versão da API (sem token) |
| `host.get` / `hostgroup.get` / `hostinterface.get` | Inventário de hosts, grupos e interfaces |
| `item.get` | Itens monitorados e valores atuais |
| `history.get` / `trend.get` | Séries temporais |
| `graph.get` | Gráficos cadastrados |
| `problem.get` / `trigger.get` | Incidentes e triggers |
| `template.get` / `maintenance.get` | Templates e manutenções |

São todos métodos de consulta. O dashboard não disponibiliza métodos administrativos como `host.delete`.

Documentação oficial: [Referência de métodos Zabbix 7.0](https://www.zabbix.com/documentation/7.0/en/manual/api/reference).

## Operação, testes e atualização

```powershell
# Atualizar sem apagar o volume PostgreSQL
git pull origin main
docker compose up -d --build --force-recreate

# Diagnóstico
docker compose logs --tail=100 dashboard
docker compose ps

# Testes no ambiente de desenvolvimento (Python)
python -m pip install -r requirements.txt pytest
python -m pytest -q
```

Com login ativo, endpoints de diagnóstico do Flask:
- `GET /api/session`
- `GET /api/config` (não revela o token)
- `GET /api/catalog`
- `POST /api/catalog/check` (consulta permissões)
- `GET /api/snapshot`

Novos endpoints de leitura local e histórico:
- `GET /api/collector/status` — diagnóstico do coletor independente.
- `GET /api/hosts/<host_id>/items?include_gauges=1` — itens e métricas já coletados.
- `GET /api/history/local/<host_id>` — prévia do PostgreSQL, sem espera pela API.
- `GET /api/history/series/<host_id>/<cpu|memory|disk|gpu|network>?days=30` — série oficial por recurso.
- `GET /api/capacity` — picos de memória, cobertura e sugestões de remanejamento.
- `GET /api/smtp` e `GET /api/alert-groups` — configuração pública para a sessão administrativa, com estado dos envios e sem credenciais.

O GitHub Actions executa testes unitários, regressão de UI e integração com um PostgreSQL de teste. O banco corporativo não é usado nos testes.

A API Zabbix retorna dados conforme os direitos do usuário associado ao token e os itens coletados. A interface exibe taxa de rede em Mbps. A série de GPU continua disponível na API interna para compatibilidade.

## Segurança

Este repositório é **privado** e pertence à organização **Avansat-Tecnologias**. Não faça commit de `.env`, tokens, credenciais SMTP, chaves Fernet, endereços internos privados nem exportações de dados da infraestrutura. Use token dedicado e de menor privilégio possível. Nunca exponha o Flask para a internet sem autenticação forte, TLS, proteção adicional para sessão e revisão de segurança.

## Limitações da versão beta

- Alertas automáticos exigem um remetente válido, destinatários cadastrados e pelo menos um grupo ativo.
- Dados de 365 dias dependem da retenção de tendências do Zabbix; o PostgreSQL local contém apenas um mini-histórico recente.
- Na primeira instalação, os hosts são preenchidos por lotes, sem bloquear o carregamento do dashboard.
- Gráficos de rede são exibidos em Mbps; limites percentuais exigem velocidade da interface disponível no Zabbix.
- O diagnóstico de permissões realiza consultas reais, mas não garante existência de dados para cada método.
- Modelo da CPU e detalhes de módulos de RAM dependem dos itens cadastrados no Zabbix. A arquitetura ou a contagem de CPUs lógicas não identificam o modelo.

## Licença

GPL-3.0. Consulte [LICENSE](LICENSE).

## Configuração do coletor

```dotenv
POLL_INTERVAL=30
HOSTS_PER_CYCLE=8
CACHE_RETENTION_HOURS=72
```

- `POLL_INTERVAL`: intervalo entre ciclos do processo coletor (mínimo 15s).
- `HOSTS_PER_CYCLE`: quantidade máxima de hosts consultada por `item.get` a cada ciclo, de 1 a 24.
- `CACHE_RETENTION_HOURS`: histórico local em horas. Os registros antigos são removidos periodicamente.

Atualizar os serviços sem destruir dados: `docker compose up -d --build --force-recreate`. **Não execute `docker compose down -v`**, pois o volume PostgreSQL contém token e histórico.

## Envio de e-mail

Em **Configurações → Remetentes SMTP**, selecione o provedor e informe o endereço da
conta. O painel configura a porta 587 com STARTTLS. **Validar** verifica a autenticação,
**Testar** envia uma mensagem ao destinatário escolhido e **Salvar** cadastra o remetente.
As credenciais são criptografadas com a `FERNET_KEY` da implantação.

- **Gmail** usa uma [senha de app do Google](https://support.google.com/accounts/answer/185833).
- **Microsoft 365** aceita OAuth ou senha SMTP quando a
  organização permite autenticação por senha e habilita SMTP AUTH para a caixa.

Para habilitar OAuth, registre um aplicativo Web no Microsoft Entra para contas
corporativas. Adicione a permissão delegada **SMTP.Send** do Office 365 Exchange Online. Registre a URI de
redirecionamento indicada no `.env.example`, configure as três variáveis
`SMTP_MICROSOFT_*` no `.env` e recrie o container. Na interface, selecione
**Conectar com a Microsoft** e autorize a conta na página da Microsoft.

Cadastre os endereços que recebem alertas em **Destinatários de alertas**. Em
**Grupos de alerta**, associe um remetente a um ou mais destinatários e escolha
todos os servidores do painel ou uma seleção específica. Grupos ativos recebem
novos problemas do Zabbix após a ativação, respeitando a supressão no Zabbix. O coletor usa `problem.get` e
`trigger.get` para relacionar o evento aos servidores e registra os envios
para evitar duplicação entre grupos com o mesmo remetente e destinatário.
Em **Grupos de alerta**, o painel mostra os envios confirmados pelo SMTP e os envios
sem confirmação nas últimas 24 horas, além do horário da última verificação do coletor.
