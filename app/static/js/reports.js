import {requestJSON} from './api.js';
import {$, $$, setMessage} from './state.js';
import {bars, dayBuckets} from './monitor_charts.js';

const date = seconds => new Date(seconds * 1000).toLocaleString('pt-BR');
const duration = seconds => seconds == null ? '—' :
  new Intl.NumberFormat('pt-BR', {maximumFractionDigits: 1}).format(seconds / 60) + ' min';

function renderRows(selector, rows) {
  $(selector).replaceChildren(...rows.map(values => {
    const row = document.createElement('tr');
    for (const value of values) row.insertCell().textContent = value ?? '—';
    return row;
  }));
}

async function load(status, action) {
  setMessage(status, 'Consultando o Zabbix…');
  try {
    await action();
  } catch (error) {
    setMessage(status, error.message, true);
  }
}

export function initializeReports() {
  $$('[data-report]').forEach(button => button.addEventListener('click', () => {
    $$('[data-report]').forEach(tab => {
      tab.classList.toggle('active', tab === button);
      tab.setAttribute('aria-pressed', String(tab === button));
    });
    $$('[data-report-panel]').forEach(panel => {
      panel.hidden = panel.dataset.reportPanel !== button.dataset.report;
    });
  }));
  const filters = $('#incident-filters');
  const incidentUrl = () => '/api/reports/incidents?' + new URLSearchParams(new FormData(filters));
  $('[data-view="reports"]').addEventListener('click', async () => {
    const select = $('#report-groups');
    if (select.options.length > 1) return;
    try {
      for (const group of await requestJSON('/api/groups')) {
        select.add(new Option(group.name, group.groupid));
      }
    } catch (error) {
      setMessage('#incident-status', error.message, true);
    }
  });
  filters.addEventListener('submit', event => {
    event.preventDefault();
    const button = filters.querySelector('button[type="submit"], button:not([type])');
    button.disabled = true;
    load('#incident-status', async () => {
      const data = await requestJSON(incidentUrl());
      renderRows('#incident-rows', data.rows.slice(0, 200).map(row => [
        row.name, row.hosts, row.severity, date(row.opened_at),
        row.resolved ? 'Resolvido' : 'Aberto', duration(row.ack_seconds), duration(row.recovery_seconds),
      ]));
      $('#incident-visuals').hidden = !data.rows.length;
      bars('#incident-days', dayBuckets(data.rows));
      bars('#incident-recurring', data.recurring.map(entry => [entry.name, entry.count, 'info']));
      setMessage('#incident-status', data.open + ' abertos · ' + data.resolved +
        ' resolvidos · Recuperação média ' + duration(data.mean_recovery_seconds) +
        (data.rows.length > 200 ? ' · Até 200 linhas na tela' : '') +
        (data.truncated ? ' · Resultado parcial limitado a 5.000 incidentes' : ''));
    }).finally(() => { button.disabled = false; });
  });
  $('#incidents-csv').addEventListener('click', () => { window.location.assign(incidentUrl() + '&format=csv'); });
  const sla = $('#report-sla');
  $('#load-slas').addEventListener('click', () => load('#sla-status', async () => {
    const data = await requestJSON('/api/reports/slas');
    sla.replaceChildren(new Option('Selecione', ''), ...data.map(row =>
      new Option(row.name + ' · Meta ' + row.slo + '% · ' + row.timezone, row.slaid)));
    renderRows('#sla-rows', []);
    setMessage('#sla-status', data.length ? 'Selecione um SLA.' : 'Nenhum SLA ativo disponível.');
  }));
  sla.addEventListener('change', () => {
    renderRows('#sla-rows', []);
    if (!sla.value) { setMessage('#sla-status', 'Selecione um SLA.'); return; }
    load('#sla-status', async () => {
      const rows = await requestJSON('/api/reports/slas/' + encodeURIComponent(sla.value));
      renderRows('#sla-rows', rows.map(row => [
        row.service, date(row.period_from) + ' até ' + date(row.period_to),
        Number(row.sli) >= 0 ? row.sli + '%' : '—', duration(row.downtime), duration(row.error_budget),
      ]));
      setMessage('#sla-status', rows.length ? '' : 'Sem medições para este SLA.');
    });
  });
  $('#load-collection').addEventListener('click', () => load('#collection-status', async () => {
    const data = await requestJSON('/api/reports/collection');
    renderRows('#collection-rows', [
      ...data.unsupported.map(row => ['Item sem suporte', row.name, row.hosts.map(host => host.name).join(', ')]),
      ...data.web_failures.map(row => ['Falha no último teste web', row.name, row.hosts.map(host => host.name).join(', ')]),
      ...data.stale_hosts.map(row => ['Dados com mais de 1 hora', row.metrics.join(', '), row.name]),
      ...data.scenarios.map(row => ['Cenário web ativo', row.name, row.hostid]),
    ]);
    setMessage('#collection-status', data.unsupported.length + ' itens sem suporte · ' +
      data.scenarios.length + ' cenários web ativos' + (data.truncated ? ' · Resultado parcial' : ''));
  }));
}
