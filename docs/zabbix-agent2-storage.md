# Monitoramento Multi-Disco (Zabbix 7.0 + Agent 2)

Este documento explica **o que foi implementado**, **por que** e **para quê**, além dos parâmetros da API do Zabbix 7.0 e da configuração opcional no Zabbix Agent 2 para identificar discos físicos (`HDD`/`SSD`/`NVMe`) e pastas/programas com maior uso em cada volume.

---

## 1. O que mudou no dashboard e por quê

Anteriormente, o coletor e o frontend tratavam apenas o disco principal (`C:` no Windows ou `/` no Linux), porque `monitoring.gauge_metrics()` seleciona apenas um item vencedor por categoria para os indicadores circulares.

Com a inclusão de `app/services/storage.py` e sua integração em `worker.py`, `cache.py`, `host_specs.py`, `routes/monitoring.py`, `dashboard.html` e `hosts.js`:

1. **Todos os volumes (`C:`, `D:`, `E:`, `/`, `/var`, etc.)** são extraídos em `storage.volumes` com espaço **total, ocupado, livre e percentual** (via `vfs.fs.get`, `vfs.fs.dependent.size[...]` e `vfs.fs.size[...]`).
2. **Discos físicos instalados (`HDD`, `SSD`, `NVMe`)** são extraídos em `storage.physical_disks` quando coletados via `smart.disk.get`, `wmi.getall` (`MSFT_PhysicalDisk` / `Win32_DiskDrive`) ou `vfs.dev.discovery`.
3. **Pastas e programas que mais ocupam espaço** em cada volume são exibidos em um painel expansível no detalhamento da VM (via item JSON `custom.disk.top_usage` ou itens nativos `vfs.dir.size[...]`).
4. **Compatibilidade com cache existente:** `cache.get()` preenche `storage` automaticamente a partir dos `items` já salvos no PostgreSQL, sem exigir nova consulta remota ao abrir a página.

---

## 2. Parâmetros da API Zabbix 7.0 (`item.get`)

O cliente (`app/services/zabbix.py`) opera estritamente em modo somente leitura com `Authorization: Bearer <token>` em `/api_jsonrpc.php`.

Para consultar apenas itens de armazenamento em um host específico, foi adicionada a função `zabbix.storage_items(host_id)` usando os seguintes parâmetros do Zabbix 7.0:

```json
{
  "jsonrpc": "2.0",
  "method": "item.get",
  "params": {
    "hostids": ["10084"],
    "output": [
      "itemid", "hostid", "name", "key_", "lastvalue",
      "units", "value_type", "lastclock", "status", "state"
    ],
    "filter": {
      "status": 0,
      "state": 0
    },
    "search": {
      "key_": [
        "vfs.fs.", "vfs.dev.", "vfs.dir.size[",
        "smart.disk.", "wmi.getall[", "custom.disk."
      ]
    },
    "startSearch": true,
    "searchByAny": true,
    "monitored": true,
    "selectTags": ["tag", "value"],
    "selectItemDiscovery": ["itemid", "parent_itemid"]
  },
  "id": 1
}
```

### Por que cada parâmetro é usado
* `filter: {"status": 0, "state": 0}`: filtra itens habilitados (`status=0`) e suportados (`state=0` no Zabbix 7.0).
* `search.key_` + `startSearch: true` + `searchByAny: true`: busca apenas chaves que **começam** com qualquer um dos prefixos listados (`OR`).
* `monitored: true`: restringe a itens efetivamente monitorados.
* `selectTags` / `selectItemDiscovery`: retorna metadados de LLD (`Mounted filesystem discovery`) e tags do template oficial (`component: storage`, `filesystem: D:`).

---

## 3. Como habilitar no Zabbix Server / Agent 2

### A) Todos os volumes (`C:`, `D:`, `E:`, `/`, ...)
Nos templates oficiais do Zabbix 7.0 (*Windows by Zabbix agent 2* / *Linux by Zabbix agent 2*):
* O item mestre `vfs.fs.get` já retorna todos os sistemas de arquivos em JSON.
* Se um volume não aparecer nos itens dependentes (`vfs.fs.dependent.size[...]`), confira no template as macros da regra de descoberta:
  * `{$VFS.FS.DRIVETYPE.MATCHES}` (no Windows, padrão `fixed`)
  * `{$VFS.FS.FSNAME.NOT_MATCHES}`
  * `{$VFS.FS.FSTYPE.MATCHES}`

### B) Identificar se cada disco é HDD, SSD ou NVMe
* **Via SMART (Windows e Linux):** aplique o template *SMART by Zabbix agent 2* (`smart.disk.get`) e configure o `smartmontools` no `zabbix_agent2.conf`:
  ```ini
  Plugins.Smart.Path="C:\Program Files\smartmontools\bin\smartctl.exe"
  ```
* **Via WMI nativo no Windows (sem instalar `smartmontools`):** crie um item de texto (`value_type: Text`) com a chave:
  ```text
  wmi.getall[root\microsoft\windows\storage,"SELECT FriendlyName, MediaType, BusType, Size, HealthStatus FROM MSFT_PhysicalDisk"]
  ```
  *(Nota: em algumas VMs, o hypervisor apresenta discos virtuais sem `MediaType` definido; nesse caso o dashboard exibirá `Desconhecido` sem inventar o tipo).*

### C) Pastas e programas que mais pesam por disco
O Zabbix Agent 2 não possui um item nativo que ranqueie automaticamente todas as pastas/programas de cada drive. Para habilitar essa visão sem abrir `system.run` irrestrito:

1. Copie o script correspondente de `deploy/zabbix-agent2/` para a VM:
   * Windows: `deploy/zabbix-agent2/disk_top_usage.ps1`
   * Linux: `deploy/zabbix-agent2/disk_top_usage.sh`
2. Adicione o `UserParameter=custom.disk.top_usage,...` de `deploy/zabbix-agent2/userparameters.conf` no `zabbix_agent2.conf` (com `Timeout=30`) e reinicie o Agent 2.
3. No template do Zabbix, crie um item:
   * **Nome:** `Uso de disco por pasta e programa`
   * **Chave:** `custom.disk.top_usage`
   * **Tipo de informação:** `Text` (`value_type: 4`)
   * **Intervalo de atualização:** `30m` ou `1h` (para não gerar I/O excessivo)
   * **Histórico:** `1d` (ou `7d`)

Alternativamente, o dashboard também lê itens nativos `vfs.dir.size[caminho,...]` criados no Zabbix e os associa automaticamente ao volume correspondente (`C:`, `D:`, `/var`, etc.).
