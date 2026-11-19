/** Listagem de hosts e itens, com atualização incremental recebida por WebSocket. */
import {requestJSON} from './api.js';
import { $, createButton, setMessage, setText } from './state.js';

let currentHosts = [];
let selectedHost = null;
let onHistory = null;
let onWatch = null;
const severity = ['Não classificado', 'Informação', 'Aviso', 'Média', 'Alta', 'Desastre'];

export function initializeHosts(options) {
  onHistory = options.onHistory;
  onWatch = options.onWatch;
}

function hostLabel(host) {
  return host.name || host.host || host.hostid;
}

function renderHostButtons() {
  for (const selector of ['#server-tabs', '#overview-hosts']) {
    const container = $(selector);
    container.replaceChildren();
    for (const host of currentHosts) {
      const tab = createButton(hostLabel(host), () => selectHost(host));
      tab.classList.toggle('active', selectedHost?.hostid === host.hostid);
      container.append(tab);
    }
  }
}

async function selectHost(host) {
  selectedHost = host;
  renderHostButtons();
  setText('#selected-host', hostLabel(host));
  setText('#overview-summary', 'Consultando métricas de ' + hostLabel(host) + '...');
  setMessage('#server-status', 'Carregando itens do host...');
  if (onWatch) onWatch(host.hostid);
  try {
    const items = await requestJSON('/api/hosts/' +
      encodeURIComponent(host.hostid) + '/items');
    renderItems({hostid: host.hostid, items});
  } catch (error) {
    setMessage('#server-status', error.message, true);
  }
}

export function renderSnapshot(snapshot) {
  if (!snapshot || !Array.isArray(snapshot.hosts)) return;
  const kpis = snapshot.kpis || {};
  setText('#total-hosts', kpis.hosts ?? snapshot.hosts.length);
  setText('#enabled-hosts', kpis.enabled);
  setText('#total-problems', kpis.active_problems);
  const stamp = new Date(snapshot.timestamp || Date.now()).toLocaleTimeString('pt-BR');
  setText('#updated', stamp);
  setText('#config-updated', stamp);
  setMessage('#overview-status', snapshot.warning ||
    'Recebimento de métricas ativo: última coleta ' + stamp, false);

  const newIds = snapshot.hosts.map(h => h.hostid).join(',');
  const oldIds = currentHosts.map(h => h.hostid).join(',');
  currentHosts = snapshot.hosts;
  if (newIds !== oldIds) {
    const previous = selectedHost?.hostid;
    selectedHost = currentHosts.find(h => h.hostid === previous) || null;
    renderHostButtons();
    if (!selectedHost && currentHosts.length) selectHost(currentHosts[0]);
    if (!currentHosts.length) setText('#overview-summary', 'Nenhum host visível com este token.');
  }
  renderProblems(snapshot.problems || []);
}

function renderProblems(problems) {
  const tbody = $('#problems-body');
  tbody.replaceChildren();
  for (const p of problems.slice(0, 80)) {
    const row = document.createElement('tr');
    const name = document.createElement('td');
    name.textContent = p.name || 'Problema sem título';
    const level = document.createElement('td');
    level.textContent = severity[Number(p.severity)] || 'Indefinida';
    const when = document.createElement('td');
    when.textContent = p.clock ?
      new Date(Number(p.clock) * 1000).toLocaleString('pt-BR') : '—';
    row.append(name, level, when);
    tbody.append(row);
  }
  if (!problems.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 3;
    cell.textContent = 'Nenhum problema disponível nesta consulta.';
    row.append(cell);
    tbody.append(row);
  }
}

function renderGauges(items, gauges) {
  for (const containerId of ['#server-gauges', '#overview-gauges']) {
    const container = $(containerId);
    container.replaceChildren();
    const names = {
      cpu: 'CPU', memory: 'Memória RAM', disk: 'Disco',
      network_in: 'Rede RX', network_out: 'Rede TX', gpu: 'GPU',
    };
    for (const [kind, label] of Object.entries(names)) {
      const metric = gauges?.[kind];
      const card = document.createElement('article');
      card.className = 'gauge';
      const title = document.createElement('p');
      title.className = 'name';
      title.textContent = label;
      const value = document.createElement('div');
      value.className = 'value';
      value.textContent = metric ?
        String(metric.value || '0') + ' ' + (metric.units || '') : 'N/D';
      const detail = document.createElement('small');
      detail.textContent = metric ? metric.name : 'Item não identificado no Zabbix';
      // Utiliza anel de progresso apenas quando o item informa porcentagem real.
      const numeric = metric ? Number(metric.value) : NaN;
      const isPercent = metric && String(metric.units).trim() === '%' &&
        Number.isFinite(numeric) && numeric >= 0 && numeric <= 100;
      if (isPercent) {
        const ring = document.createElement('div');
        ring.className = 'progress-ring';
        ring.style.setProperty('--progress', numeric + '%');
        ring.setAttribute('role', 'img');
        ring.setAttribute('aria-label', label + ': ' + numeric + '%');
        const text = document.createElement('span');
        text.textContent = numeric.toFixed(1) + '%';
        ring.append(text);
        card.append(title, ring, detail);
      } else {
        card.append(title, value, detail);
      }
      container.append(card);
    }
  }
}

function inferGauges(items) {
  const selectors = {
    cpu: it => String(it.key_).startsWith('system.cpu.util'),
    memory: it => String(it.key_).startsWith('vm.memory.util') ||
      String(it.key_) === 'vm.memory.size[pused]',
    disk: it => String(it.key_).startsWith('vfs.fs.size[') &&
      String(it.key_).includes('pused'),
    network_in: it => String(it.key_).startsWith('net.if.in['),
    network_out: it => String(it.key_).startsWith('net.if.out['),
    gpu: it => String(it.key_).toLowerCase().includes('gpu.util'),
  };
  return Object.fromEntries(Object.entries(selectors).flatMap(([key, filter]) => {
    const item = items.find(filter);
    return item ? [[key, item]] : [];
  }));
}

export function renderItems(payload) {
  if (!selectedHost || String(payload.hostid) !== String(selectedHost.hostid)) return;
  const items = payload.items || [];
  const tbody = $('#items');
  tbody.replaceChildren();
  setText('#overview-summary', hostLabel(selectedHost) +
    ' · ' + items.length + ' itens monitorados');
  renderGauges(items, payload.gauges || inferGauges(items));
  const limit = 500;
  for (const item of items.slice(0, limit)) {
    const row = document.createElement('tr');
    const name = document.createElement('td');
    name.textContent = item.name || item.key_ || 'Item';
    const value = document.createElement('td');
    value.textContent = (item.lastvalue ?? '—') + ' ' + (item.units || '');
    const actions = document.createElement('td');
    if (['0', '3'].includes(String(item.value_type))) {
      actions.append(createButton('Histórico', () => onHistory(item), 'btn secondary'));
    } else {
      actions.textContent = '—';
    }
    row.append(name, value, actions);
    tbody.append(row);
  }
  setMessage('#server-status', items.length > limit ?
    'Exibindo os primeiros ' + limit + ' de ' + items.length + ' itens.' :
    'Itens atualizados: ' + items.length);
}

export function showHostError(error) {
  setMessage('#server-status', error.message || 'Falha ao consultar host.', true);
}
