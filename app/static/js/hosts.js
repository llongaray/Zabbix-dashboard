/**
 * Apresentação de hosts e métricas.
 * Seleção filtrável para dezenas de hosts; sem reflows horizontais.
 * Não classificamos itens Zabbix por prefixo aqui: o backend valida a semântica.
 */
import {requestJSON} from './api.js';
import {$, $$, createButton, setMessage, setText} from './state.js';

let currentHosts = [];
let selectedHost = null;
let currentItems = [];
let onHistory = null;
let onWatch = null;

const severities = ['Não classificado', 'Informação', 'Aviso', 'Média', 'Alta', 'Desastre'];
const gaugeLabels = {
  cpu: 'CPU',
  memory: 'Memória RAM',
  disk: 'Disco',
  network_in: 'Banda recebida (RX)',
  network_out: 'Banda enviada (TX)',
  gpu: 'GPU',
};

function hostLabel(host) {
  return host?.name || host?.host || String(host?.hostid || 'Host');
}

export function getSelectedHostId() {
  return selectedHost?.hostid || null;
}

export function initializeHosts({onHistory: history, onWatch: watch} = {}) {
  onHistory = history;
  onWatch = watch;
  for (const id of ['#overview-host-search', '#server-host-search']) {
    $(id)?.addEventListener('input', renderHostButtons);
  }
  $('#item-search')?.addEventListener('input', renderItemTable);
  for (const arrow of $$('[data-scroll-target]')) {
    arrow.addEventListener('click', () => {
      const target = document.getElementById(arrow.dataset.scrollTarget);
      const direction = Number(arrow.dataset.scrollDir) || 1;
      target?.scrollBy({left: direction * Math.max(250, target.clientWidth * 0.7),
        behavior: 'smooth'});
    });
  }
}

function renderHostButtons() {
  const rails = [
    ['#overview-hosts', '#overview-host-search', '#overview-host-count'],
    ['#server-tabs', '#server-host-search', '#server-host-count'],
  ];
  for (const [id, searchId, countId] of rails) {
    const element = $(id);
    if (!element) continue;
    const scrollX = element.scrollLeft;
    const query = ($(searchId)?.value || '').trim().toLocaleLowerCase('pt-BR');
    const filtered = currentHosts.filter(host =>
      hostLabel(host).toLocaleLowerCase('pt-BR').includes(query));
    const fragment = document.createDocumentFragment();
    for (const host of filtered) {
      const button = createButton(hostLabel(host), () => selectHost(host));
      button.title = hostLabel(host);
      button.classList.toggle('active', selectedHost?.hostid === host.hostid);
      fragment.append(button);
    }
    if (!filtered.length) {
      const hint = document.createElement('span');
      hint.className = 'muted';
      hint.textContent = 'Nenhum servidor encontrado.';
      fragment.append(hint);
    }
    element.replaceChildren(fragment);
    element.scrollLeft = scrollX;
    setText(countId, filtered.length + ' de ' + currentHosts.length + ' hosts');
  }
}

async function selectHost(host) {
  selectedHost = host;
  renderHostButtons();
  setText('#selected-host', hostLabel(host));
  setText('#overview-summary', 'Consultando ' + hostLabel(host) + '…');
  setMessage('#server-status', 'Consultando itens do Zabbix...');
  onWatch?.(String(host.hostid));
  try {
    const payload = await requestJSON('/api/hosts/' +
      encodeURIComponent(host.hostid) + '/items?include_gauges=1');
    renderItems(payload);
  } catch (error) {
    if (selectedHost?.hostid === host.hostid) {
      setMessage('#server-status', error.message, true);
      renderGauges({});
    }
  }
}

export function renderSnapshot(snapshot) {
  if (!Array.isArray(snapshot?.hosts)) return;
  const kpi = snapshot.kpis || {};
  setText('#total-hosts', kpi.hosts ?? snapshot.hosts.length);
  setText('#enabled-hosts', kpi.enabled);
  setText('#total-problems', kpi.active_problems == null ? 'N/D' :
    (kpi.problems_limited ? '≥ ' : '') + kpi.active_problems);
  const stamp = new Date(snapshot.timestamp || Date.now()).toLocaleTimeString('pt-BR');
  setText('#updated', stamp);
  setText('#config-updated', stamp);
  setMessage('#overview-status', snapshot.warning ||
    'Coleta recebida às ' + stamp, !!snapshot.warning);

  const previousIds = currentHosts.map(host => String(host.hostid)).join(',');
  const nextIds = snapshot.hosts.map(host => String(host.hostid)).join(',');
  currentHosts = snapshot.hosts;
  if (previousIds !== nextIds) {
    const currentId = selectedHost?.hostid;
    selectedHost = currentHosts.find(host => host.hostid === currentId) || null;
    renderHostButtons();
    if (!selectedHost && currentHosts.length) {
      void selectHost(currentHosts[0]);
    } else if (!currentHosts.length) {
      setText('#overview-summary', 'Nenhum host disponível com este token.');
      renderGauges({});
    }
  }
  renderProblems(snapshot.problems || []);
}

function renderProblems(problems) {
  const tbody = $('#problems-body');
  if (!tbody) return;
  const fragment = document.createDocumentFragment();
  for (const problem of problems.slice(0, 80)) {
    const row = document.createElement('tr');
    for (const label of [
      problem.name || 'Problema sem nome',
      severities[Number(problem.severity)] || 'Não classificado',
      problem.clock ? new Date(Number(problem.clock) * 1000)
        .toLocaleString('pt-BR') : '—',
    ]) {
      const cell = document.createElement('td');
      cell.textContent = label;
      row.append(cell);
    }
    fragment.append(row);
  }
  if (!problems.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 3;
    cell.textContent = 'Não há problemas nesta consulta.';
    row.append(cell);
    fragment.append(row);
  }
  tbody.replaceChildren(fragment);
}

function renderGauges(gauges) {
  for (const selector of ['#server-gauges', '#overview-gauges']) {
    const container = $(selector);
    if (!container) continue;
    const fragment = document.createDocumentFragment();
    for (const [kind, name] of Object.entries(gaugeLabels)) {
      const metric = gauges?.[kind];
      const card = document.createElement('article');
      card.className = 'gauge';
      const heading = document.createElement('p');
      heading.className = 'name';
      heading.textContent = name;
      const detail = document.createElement('small');
      detail.title = metric?.name || '';
      detail.textContent = metric?.name || 'Métrica não disponível no Zabbix';
      if (metric && metric.stale) {
        const stale = document.createElement('span');
        stale.className = 'metric-stale';
        stale.textContent = 'Leitura desatualizada · ';
        detail.prepend(stale);
      }
      const value = Number(metric?.value);
      const percent = metric && metric.units === '%' &&
        Number.isFinite(value) && value >= 0 && value <= 100;
      if (percent) {
        const ring = document.createElement('div');
        ring.className = 'progress-ring';
        ring.style.setProperty('--progress', value + '%');
        ring.setAttribute('role', 'img');
        ring.setAttribute('aria-label', name + ': ' + value.toFixed(1) + '%');
        const text = document.createElement('span');
        text.textContent = value.toFixed(1) + '%';
        ring.append(text);
        card.append(heading, ring, detail);
      } else {
        const number = document.createElement('div');
        number.className = 'value';
        number.textContent = metric ? String(metric.value) + ' ' +
          (metric.units || '') : 'N/D';
        card.append(heading, number, detail);
      }
      fragment.append(card);
    }
    container.replaceChildren(fragment);
  }
}

function renderItemTable() {
  const tbody = $('#items');
  if (!tbody) return;
  const query = ($('#item-search')?.value || '').trim().toLocaleLowerCase('pt-BR');
  const filtered = currentItems.filter(item =>
    ((item.name || '') + ' ' + (item.key_ || ''))
      .toLocaleLowerCase('pt-BR').includes(query));
  const limit = 150;
  const fragment = document.createDocumentFragment();
  for (const item of filtered.slice(0, limit)) {
    const row = document.createElement('tr');
    const name = document.createElement('td');
    name.textContent = item.name || item.key_ || 'Item';
    const value = document.createElement('td');
    value.textContent = (item.lastvalue ?? '—') + ' ' + (item.units || '');
    const actions = document.createElement('td');
    if (['0', '3'].includes(String(item.value_type))) {
      actions.append(createButton('Histórico', () => onHistory?.(item),
        'btn secondary'));
    } else {
      actions.textContent = 'Não numérico';
    }
    row.append(name, value, actions);
    fragment.append(row);
  }
  if (!filtered.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 3;
    cell.textContent = 'Nenhum item encontrado.';
    row.append(cell);
    fragment.append(row);
  }
  tbody.replaceChildren(fragment);
  setMessage('#server-status',
    filtered.length > limit ? 'Exibindo ' + limit + ' de ' +
      filtered.length + ' itens. Filtre para localizar outros.' :
      filtered.length + ' itens visíveis (' + currentItems.length + ' no host).');
}

export function renderItems(payload) {
  if (!selectedHost || String(payload?.hostid) !== String(selectedHost.hostid)) {
    return;
  }
  currentItems = payload.items || [];
  setText('#overview-summary', hostLabel(selectedHost) + ' · ' +
    currentItems.length + ' itens disponíveis');
  // Não inferir métricas de rede no frontend; apenas dados validados pelo backend.
  renderGauges(payload.gauges || {});
  renderCoverage(payload.diagnostics || {});
  renderItemTable();
}

export function showHostError(error) {
  setMessage('#server-status', error.message || 'Falha ao consultar host.', true);
}

export function showHostPending(event) {
  if (String(event?.hostid) === String(selectedHost?.hostid)) {
    setMessage('#server-status', event.message ||
      'Aguardando o worker coletar este servidor.');
    setText('#overview-summary', 'Servidor aguardando a primeira coleta');
  }
}

function renderCoverage(diagnostics) {
  const container = $('#server-coverage');
  if (!container) return;
  const fragment = document.createDocumentFragment();
  const labels = {
    cpu: 'CPU', memory: 'RAM', disk: 'Disco',
    gpu: 'GPU', network_in: 'Rede RX', network_out: 'Rede TX',
  };
  for (const [kind, info] of Object.entries(diagnostics)) {
    if (info.available) continue;
    const line = document.createElement('p');
    line.className = 'coverage-warning';
    line.textContent = (labels[kind] || kind) + ': ' +
      (info.reason || 'Sem item válido') + ' ' + (info.suggestion || '');
    fragment.append(line);
  }
  container.replaceChildren(fragment);
}
