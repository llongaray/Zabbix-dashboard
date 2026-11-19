/** História por host: primeiro cache persistido, depois Zabbix oficial. */
import {requestJSON} from './api.js';
import {getSelectedHostId} from './hosts.js';
import {$, setMessage, showView} from './state.js';
import {clearHistoryCharts, renderLocal, renderMetric} from './history_charts.js';

const metrics = ['cpu', 'memory', 'gpu', 'network'];
let knownHosts = [];
let lastLoaded = '';
let lastRequestTime = 0;
let generation = 0;

export function updateHistoryHosts(hosts) {
  if (!Array.isArray(hosts)) return;
  const select = $('#history-host');
  if (!select) return;
  const prior = select.value || String(getSelectedHostId() || '');
  knownHosts = hosts;
  const fragment = document.createDocumentFragment();
  for (const host of knownHosts) {
    const option = document.createElement('option');
    option.value = String(host.hostid);
    option.textContent = host.name || host.host || option.value;
    fragment.append(option);
  }
  select.replaceChildren(fragment);
  const exists = knownHosts.some(host => String(host.hostid) === prior);
  select.value = exists ? prior : String(knownHosts[0]?.hostid || '');
}

function markLoading() {
  for (const kind of metrics) {
    const badge = $('#history-badge-' + kind);
    if (badge) badge.textContent = 'Sincronizando';
    setMessage('#history-message-' + kind, 'Consultando Zabbix...');
  }
}

async function loadLocal(hostId, generationId) {
  try {
    const response = await requestJSON('/api/history/local/' + hostId + '?days=2');
    if (generation !== generationId) return;
    for (const metric of metrics) renderLocal(metric, response.series);
    setMessage('#chart-status', 'Prévia local exibida. Atualizando via API oficial...');
  } catch (error) {
    setMessage('#chart-status', 'Cache local indisponível: ' + error.message, true);
  }
}

async function loadOfficial(hostId, days, kind, generationId) {
  try {
    const result = await requestJSON('/api/history/series/' + hostId + '/' +
      kind + '?days=' + days);
    if (generation !== generationId) return;
    renderMetric(kind, result, 'Zabbix ' +
      (result.series?.[0]?.source || result.source || 'history/trend'));
  } catch (error) {
    if (generation !== generationId) return;
    // Mantém o último gráfico do cache em vez de apagá-lo após erro de rede.
    setMessage('#history-message-' + kind,
      'Falha na consulta oficial; prévia local preservada. ' + error.message, true);
  }
}

async function loadHistory({force = false} = {}) {
  const hostId = String($('#history-host')?.value || getSelectedHostId() || '');
  const days = Number($('#days')?.value || 1);
  if (!hostId) {
    setMessage('#chart-status', 'Selecione um servidor para carregar o histórico.');
    return;
  }
  const key = hostId + ':' + days;
  if (!force && key === lastLoaded && Date.now() - lastRequestTime < 60000) {
    return;
  }
  lastLoaded = key;
  lastRequestTime = Date.now();
  generation++;
  const currentGeneration = generation;
  clearHistoryCharts();
  markLoading();
  setMessage('#chart-status', 'Carregando mini-histórico PostgreSQL...');
  // Não espera um request remoto para renderizar o primeiro gráfico.
  await loadLocal(hostId, currentGeneration);
  if (generation !== currentGeneration) return;
  setMessage('#chart-status', 'Sincronização histórica via API Zabbix em andamento...');
  const results = await Promise.allSettled(metrics.map(kind =>
    loadOfficial(hostId, days, kind, currentGeneration)));
  if (generation === currentGeneration) {
    const failed = results.filter(row => row.status === 'rejected').length;
    setMessage('#chart-status', failed ?
      'Sincronização parcial: verifique o estado dos gráficos.' :
      'Consulta do histórico concluída para ' + days + ' dia(s).');
  }
}

export function initializeHistory() {
  $('#days').addEventListener('change', () => void loadHistory({force: true}));
  $('#history-host').addEventListener('change', () => void loadHistory({force: true}));
  $('#refresh-history').addEventListener('click',
    () => void loadHistory({force: true}));
  document.querySelector('[data-view="history"]')
    ?.addEventListener('click', () => void loadHistory());
}

export function openHistory(item) {
  showView('history');
  const selected = String(getSelectedHostId() || '');
  if (selected && knownHosts.some(host => String(host.hostid) === selected)) {
    $('#history-host').value = selected;
  }
  // Ao clicar em "Histórico" dentro de um item, mostra todos os quesitos.
  if (item) setMessage('#chart-status', 'Carregando métricas de ' +
    (item.name || 'servidor') + ' e demais recursos do host...');
  void loadHistory({force: true});
}
