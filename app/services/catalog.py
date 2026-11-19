"""Catálogo declarativo de métodos de leitura da API Zabbix 7.0.

Todos usam POST /api_jsonrpc.php. Não expomos operações de escrita.
"""
METHODS = (
    ("apiinfo.version", "Versão", "Informações sobre a API", False),
    ("host.get", "Servidores", "Hosts e suas configurações", True),
    ("hostgroup.get", "Grupos", "Agrupamentos de servidores", True),
    ("hostinterface.get", "Interfaces", "IPs e interfaces dos hosts", True),
    ("item.get", "Itens", "Métricas coletadas pelo Zabbix", True),
    ("history.get", "Histórico", "Amostras históricas dos itens", True),
    ("trend.get", "Tendências", "Mínimo, máximo e média por hora", True),
    ("graph.get", "Gráficos", "Definições dos gráficos cadastrados", True),
    ("problem.get", "Problemas", "Incidentes monitorados", True),
    ("trigger.get", "Gatilhos", "Condições de disparo de alertas", True),
    ("template.get", "Templates", "Modelos aplicados aos hosts", True),
    ("maintenance.get", "Manutenções", "Janelas de manutenção", True),
)

ALLOWED_METHODS = frozenset(row[0] for row in METHODS)

PROBES = {
    "host.get": {"output": ["hostid"], "limit": 1},
    "hostgroup.get": {"output": ["groupid"], "limit": 1},
    "hostinterface.get": {"output": ["interfaceid"], "limit": 1},
    "item.get": {"output": ["itemid"], "limit": 1},
    "graph.get": {"output": ["graphid"], "limit": 1},
    "problem.get": {"output": ["eventid"], "limit": 1},
    "trigger.get": {"output": ["triggerid"], "limit": 1},
    "template.get": {"output": ["templateid"], "limit": 1},
    "maintenance.get": {"output": ["maintenanceid"], "limit": 1},
}


def methods():
    return [
        {"method": name, "label": label, "description": description,
         "requires_token": requires_token}
        for name, label, description, requires_token in METHODS
    ]
