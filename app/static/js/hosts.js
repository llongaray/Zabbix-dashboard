/**
 * Apresentação de hosts e métricas.
 * Seleção filtrável para dezenas de hosts; sem reflows horizontais.
 * Não classificamos itens Zabbix por prefixo aqui: o backend valida a semântica.
 */
import {appPath, requestJSON} from './api.js';
import {$, $$, createButton, setMessage, setText} from './state.js';

let currentHosts = [];
let selectedHost = null;
let currentItems = [];
let trendHost = '';
let trendSeries = {};
let trendRequestedAt = null;

function refreshTrends(hostId, gauges) {
  if (trendHost !== hostId) {
    trendHost = hostId;
    trendSeries = {};
    trendRequestedAt = null;
  }
  if (!Object.keys(gauges).length ||
      (trendRequestedAt !== null && Date.now() - trendRequestedAt < 60000)) return;
  const requestedAt = trendRequestedAt = Date.now();
  requestJSON('/api/history/local/' + encodeURIComponent(hostId) + '?days=1')
    .then(payload => {
      if (String(selectedHost?.hostid) !== hostId || trendRequestedAt !== requestedAt) return;
      trendSeries = payload.series || {};
      renderTrendLines();
    }).catch(() => {
      if (String(selectedHost?.hostid) === hostId && trendRequestedAt === requestedAt) renderTrendLines();
    });
}

function renderTrendLines() {
  for (const slot of $$('[data-metric-trend]')) {
    const kind = slot.dataset.metricTrend;
    const now = Date.now() / 1000;
    const samples = (trendSeries[kind] || []).filter(sample =>
      Number.isFinite(sample.value) && sample.units === slot.dataset.units &&
      sample.clock >= now - 6 * 3600 && sample.clock <= now);
    slot.replaceChildren();
    if (samples.length < 2) {
      slot.textContent = 'Histórico insuficiente nas últimas 6 h';
      continue;
    }
    const canvas = document.createElement('canvas');
    canvas.width = 480;
    canvas.height = 112;
    canvas.setAttribute('role', 'img');
    const format = new Intl.NumberFormat('pt-BR', {maximumFractionDigits: 2});
    const minimum = Math.min(...samples.map(sample => sample.value));
    const maximum = Math.max(...samples.map(sample => sample.value));
    canvas.setAttribute('aria-label', 'Últimas 6 horas · mínimo ' +
      format.format(minimum) + ' · máximo ' + format.format(maximum) + ' ' + slot.dataset.units);
    slot.append(canvas);
    const context = canvas.getContext('2d');
    if (!context) continue;
    const scale = kind === 'cpu' || kind === 'memory' ? 100 : Math.max(maximum, 0.001);
    context.strokeStyle = getComputedStyle(slot).getPropertyValue('--siga-color-primary').trim();
    context.lineWidth = 3;
    context.lineJoin = 'round';
    context.lineCap = 'round';
    const start = samples[0].clock;
    const span = Math.max(1, samples.at(-1).clock - start);
    context.beginPath();
    samples.forEach((sample, index) => {
      const x = 3 + (sample.clock - start) / span * 474;
      const y = 106 - Math.min(1, Math.max(0, sample.value / scale)) * 100;
      if (!index || sample.clock - samples[index - 1].clock > 3600) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    context.stroke();
    const caption = document.createElement('small');
    caption.textContent = 'Últimas 6 h · pico ' + format.format(maximum) + ' ' + slot.dataset.units;
    slot.append(caption);
  }
}

new MutationObserver(renderTrendLines).observe(document.documentElement, {
  attributes: true, attributeFilter: ['data-theme'],
});
let onHistory = null;
let onWatch = null;

const severities = ['Não classificado', 'Informação', 'Aviso', 'Média', 'Alta', 'Desastre'];
const gaugeLabels = {
  cpu: 'CPU',
  memory: 'Memória RAM',
  disk: 'Disco',
  network_in: 'Banda recebida (RX)',
  network_out: 'Banda enviada (TX)',
};
const gaugeIcons = {cpu: 'cpu', memory: 'ram', disk: 'disk', network_in: 'download', network_out: 'upload'};
const hostStatuses = {
  online: 'Online', unreachable: 'Sem resposta ao ping',
  recent: 'Coleta recente', stale: 'Coleta desatualizada', disabled: 'Desabilitado',
  pending: 'Aguardando coleta',
};
const capacityFormat = new Intl.NumberFormat('pt-BR', {maximumFractionDigits: 1});

function metricIcon(name) {
  const namespace = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(namespace, 'svg');
  const use = document.createElementNS(namespace, 'use');
  svg.setAttribute('class', 'icon');
  svg.setAttribute('aria-hidden', 'true');
  use.setAttribute('href', appPath('/static/monitor-icons.svg') + '#' + name);
  svg.append(use);
  return svg;
}

function cardLine(icon, text) {
  const line = document.createElement('span');
  line.className = 'host-card-line';
  line.append(metricIcon(icon), text);
  return line;
}

function formatBytes(bytes) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value < 0) return 'N/D';
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];
  let unit = 0;
  let scaled = value;
  while (scaled >= 1024 && unit < units.length - 1) {
    scaled /= 1024;
    unit++;
  }
  return (unit === 0 ? Math.round(scaled) : capacityFormat.format(scaled)) + ' ' + units[unit];
}

function hostCard(host) {
  const button = createButton('', () => selectHost(host), 'host-card');
  button.setAttribute('aria-controls', 'overview-host-detail');
  const summary = host.summary || {};
  const specs = summary.specs || {};
  const heading = cardLine('server', hostLabel(host));
  heading.classList.add('host-card-title');
  const osIcon = ['windows', 'linux'].includes(specs.os_family) ? specs.os_family : 'monitor';
  const cpu = specs.cpu_model || (specs.logical_cpus ? specs.logical_cpus + ' CPUs lógicas' : 'Modelo de CPU não coletado');
  const formatCapacity = bytes => capacityFormat.format(bytes / 1024 ** 3) + ' GiB';
  const ram = specs.ram_bytes ? formatCapacity(specs.ram_bytes) + ' RAM' : 'RAM não coletada';
  let disk = 'Disco total não coletado';
  if (summary.disks_count > 1 && summary.disks_total_bytes) {
    disk = formatBytes(summary.disks_total_bytes) + ' · ' + summary.disks_count + ' volumes';
  } else if (summary.disk_bytes) {
    disk = formatCapacity(summary.disk_bytes) + ' · Volume ' + summary.disk_volume;
  }
  const health = host.status === '1' ? 'disabled' : summary.status || 'pending';
  const status = document.createElement('span');
  status.className = 'host-card-status';
  status.dataset.health = health;
  status.textContent = hostStatuses[health];
  button.append(heading, cardLine(osIcon, specs.os || 'Sistema operacional não coletado'),
    cardLine('cpu', cpu), cardLine('ram', ram), cardLine('disk', disk), status);
  return button;
}

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
    const focused = element.contains(document.activeElement) ? document.activeElement.dataset.hostId : null;
    const query = ($(searchId)?.value || '').trim().toLocaleLowerCase('pt-BR');
    const filtered = currentHosts.filter(host =>
      hostLabel(host).toLocaleLowerCase('pt-BR').includes(query));
    const fragment = document.createDocumentFragment();
    for (const host of filtered) {
      const button = id === '#overview-hosts' ? hostCard(host) :
        createButton(hostLabel(host), () => selectHost(host));
      button.title = hostLabel(host);
      button.dataset.hostId = String(host.hostid);
      const active = selectedHost?.hostid === host.hostid;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
      fragment.append(button);
    }
    if (!filtered.length) {
      const hint = document.createElement('span');
      hint.className = 'muted';
      hint.textContent = 'Nenhum servidor encontrado.';
      fragment.append(hint);
    }
    element.replaceChildren(fragment);
    if (focused) Array.from(element.children).find(child => child.dataset.hostId === focused)?.focus({preventScroll: true});
    element.scrollLeft = scrollX;
    setText(countId, filtered.length + ' de ' + currentHosts.length + ' hosts');
  }
}

async function selectHost(host) {
  selectedHost = host;
  $$('[data-host-specs]').forEach(panel => { panel.hidden = true; });
  $$('[data-host-storage]').forEach(panel => { panel.hidden = true; });
  renderHostButtons();
  $('#overview-gauges').replaceChildren();
  $('#server-gauges').replaceChildren();
  setText('#overview-selected-host', hostLabel(host));
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

  const changed = JSON.stringify(currentHosts) !== JSON.stringify(snapshot.hosts);
  currentHosts = snapshot.hosts;
  if (changed) {
    const currentId = selectedHost?.hostid;
    selectedHost = currentHosts.find(host => host.hostid === currentId) || null;
    renderHostButtons();
    if (!selectedHost && currentHosts.length) {
      void selectHost(currentHosts[0]);
    }
  }
  if (!currentHosts.length) {
    renderHostButtons();
    setText('#overview-summary', snapshot.status === 'warming_up' ?
      'Aguardando a primeira coleta.' : 'Nenhum servidor com métricas de infraestrutura coletadas.');
    setText('#selected-host', 'Nenhum servidor disponível');
    setText('#overview-selected-host', 'Métricas do servidor');
    setMessage('#server-status', '');
    $('#items').replaceChildren();
    $('#server-coverage').replaceChildren();
    $('#overview-gauges').replaceChildren();
    $('#server-gauges').replaceChildren();
    $$('[data-host-specs]').forEach(panel => { panel.hidden = true; });
    $$('[data-host-storage]').forEach(panel => { panel.hidden = true; });
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
      if (['cpu', 'memory', 'disk'].includes(kind)) card.classList.add('gauge-percentage');
      const heading = document.createElement('p');
      heading.className = 'name';
      heading.append(metricIcon(gaugeIcons[kind]), name);
      const detail = document.createElement('small');
      detail.className = 'gauge-detail';
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
        ring.style.setProperty('--progress', value * 1.8 + 'deg');
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
      if (metric && kind !== 'disk') {
        const trend = document.createElement('div');
        trend.className = 'gauge-trend';
        trend.dataset.metricTrend = kind;
        trend.dataset.units = metric.units;
        card.insertBefore(trend, detail);
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

function renderSpecifications(specs) {
  const ram = specs.ram_bytes ? new Intl.NumberFormat('pt-BR', {maximumFractionDigits: 1})
    .format(specs.ram_bytes / 1024 ** 3) + ' GiB' : 'Não coletada';
  const values = {
    os: specs.os || 'Não coletado',
    architecture: specs.architecture || '',
    'cpu-model': specs.cpu_model || 'Modelo não coletado',
    'logical-cpus': specs.logical_cpus ? specs.logical_cpus + ' CPUs lógicas' : '',
    'ram-total': ram,
  };
  for (const panel of $$('[data-host-specs]')) {
    for (const [field, value] of Object.entries(values)) {
      panel.querySelector('[data-spec="' + field + '"]').textContent = value;
    }
    panel.querySelector('.os-windows').toggleAttribute('hidden', specs.os_family !== 'windows');
    panel.querySelector('.os-linux').toggleAttribute('hidden', specs.os_family !== 'linux');
    panel.hidden = false;
  }
}

function renderTopUsageGroup(title, entries, totalBytes) {
  const wrapper = document.createElement('div');
  const heading = document.createElement('p');
  heading.className = 'storage-top-title';
  heading.textContent = title;
  const list = document.createElement('ul');
  list.className = 'storage-top-list';
  for (const entry of entries) {
    const item = document.createElement('li');
    const label = document.createElement('span');
    label.textContent = entry.path && entry.path !== entry.name ?
      entry.name + ' (' + entry.path + ')' : (entry.name || entry.path);
    label.title = entry.path || entry.name || '';
    const size = document.createElement('strong');
    const share = totalBytes ? ' (' + capacityFormat.format(entry.bytes * 100 / totalBytes) + '%)' : '';
    size.textContent = formatBytes(entry.bytes) + share;
    item.append(label, size);
    list.append(item);
  }
  wrapper.append(heading, list);
  return wrapper;
}

function renderStorage(storageData) {
  const volumes = Array.isArray(storageData?.volumes) ? storageData.volumes : [];
  const physical = Array.isArray(storageData?.physical_disks) ? storageData.physical_disks : [];
  const totals = storageData?.totals || {};

  for (const panel of $$('[data-host-storage]')) {
    const summaryEl = panel.querySelector('[data-storage-summary]');
    const physicalEl = panel.querySelector('[data-storage-physical]');
    const volumesEl = panel.querySelector('[data-storage-volumes]');
    if (!volumes.length && !physical.length) {
      panel.hidden = true;
      continue;
    }

    const summaryParts = [];
    if (volumes.length) summaryParts.push(volumes.length + (volumes.length === 1 ? ' volume' : ' volumes'));
    if (physical.length) summaryParts.push(physical.length + (physical.length === 1 ? ' disco físico' : ' discos físicos'));
    if (totals.total_bytes) summaryParts.push(formatBytes(totals.total_bytes) + ' total');
    if (totals.free_bytes != null) summaryParts.push(formatBytes(totals.free_bytes) + ' livre');
    summaryEl.textContent = summaryParts.join(' · ');

    if (physical.length) {
      const chipFragment = document.createDocumentFragment();
      for (const disk of physical) {
        const chip = document.createElement('div');
        chip.className = 'storage-disk-chip';
        const badge = document.createElement('span');
        badge.className = 'storage-media-badge';
        badge.dataset.media = disk.media_type || 'Desconhecido';
        badge.textContent = disk.media_type || 'Disco';
        const info = [disk.name || disk.model || disk.id];
        if (disk.size_bytes) info.push(formatBytes(disk.size_bytes));
        if (disk.bus_type) info.push(disk.bus_type);
        if (disk.health) info.push(disk.health);
        if (Number.isFinite(disk.temperature_c)) info.push(disk.temperature_c + ' °C');
        const text = document.createElement('span');
        text.textContent = info.join(' · ');
        chip.append(badge, text);
        chipFragment.append(chip);
      }
      physicalEl.replaceChildren(chipFragment);
      physicalEl.hidden = false;
    } else {
      physicalEl.replaceChildren();
      physicalEl.hidden = true;
    }

    const volFragment = document.createDocumentFragment();
    for (const vol of volumes) {
      const card = document.createElement('article');
      card.className = 'storage-volume';

      const head = document.createElement('div');
      head.className = 'storage-volume-head';
      const titleBox = document.createElement('div');
      const title = document.createElement('div');
      title.className = 'storage-volume-title';
      title.textContent = vol.volume + (vol.label ? ' (' + vol.label + ')' : '');
      const meta = document.createElement('div');
      meta.className = 'storage-volume-meta';
      const metaParts = [];
      if (vol.fstype) metaParts.push(vol.fstype);
      if (vol.drivetype) metaParts.push(vol.drivetype);
      if (vol.stale) metaParts.push('leitura desatualizada');
      meta.textContent = metaParts.join(' · ') || 'Volume monitorado';
      titleBox.append(title, meta);

      const pct = Number(vol.used_pct);
      const hasPct = Number.isFinite(pct) && pct >= 0 && pct <= 100;
      const pctLabel = document.createElement('span');
      pctLabel.className = 'storage-volume-pct';
      pctLabel.textContent = hasPct ? pct.toFixed(1) + '%' : 'N/D';
      head.append(titleBox, pctLabel);

      const bar = document.createElement('div');
      bar.className = 'storage-bar';
      bar.setAttribute('aria-hidden', 'true');
      const fill = document.createElement('i');
      if (hasPct) {
        fill.style.width = pct + '%';
        if (pct >= 90) fill.dataset.tone = 'danger';
        else if (pct >= 80) fill.dataset.tone = 'warning';
      } else {
        fill.style.width = '0%';
      }
      bar.append(fill);

      const metrics = document.createElement('div');
      metrics.className = 'storage-metrics';
      const freePct = Number.isFinite(Number(vol.free_pct)) ?
        ' (' + Number(vol.free_pct).toFixed(1) + '%)' : '';
      for (const [label, value] of [
        ['Total', vol.total_bytes != null ? formatBytes(vol.total_bytes) : 'N/D'],
        ['Ocupado', vol.used_bytes != null ? formatBytes(vol.used_bytes) : 'N/D'],
        ['Livre', (vol.free_bytes != null ? formatBytes(vol.free_bytes) : 'N/D') + freePct],
      ]) {
        const cell = document.createElement('div');
        const cap = document.createElement('span');
        cap.textContent = label;
        const val = document.createElement('strong');
        val.textContent = value;
        cell.append(cap, val);
        metrics.append(cell);
      }

      const details = document.createElement('details');
      details.className = 'storage-top';
      const summary = document.createElement('summary');
      const topDirs = Array.isArray(vol.top_dirs) ? vol.top_dirs : [];
      const topApps = Array.isArray(vol.top_apps) ? vol.top_apps : [];
      summary.textContent = (topDirs.length || topApps.length) ?
        'Pastas e programas com maior uso (' + (topDirs.length + topApps.length) + ')' :
        'Pastas e programas com maior uso (não coletado)';
      const body = document.createElement('div');
      body.className = 'storage-top-body';
      if (topDirs.length) body.append(renderTopUsageGroup('Pastas mais pesadas', topDirs, vol.total_bytes));
      if (topApps.length) body.append(renderTopUsageGroup('Programas / aplicativos', topApps, vol.total_bytes));
      if (!topDirs.length && !topApps.length) {
        const hint = document.createElement('p');
        hint.className = 'muted storage-empty';
        hint.textContent = 'Sem item custom.disk.top_usage ou vfs.dir.size[*] habilitado no Zabbix Agent 2 para este volume.';
        body.append(hint);
      }
      details.append(summary, body);

      card.append(head, bar, metrics, details);
      volFragment.append(card);
    }

    if (!volumes.length) {
      const hint = document.createElement('p');
      hint.className = 'muted storage-empty';
      hint.textContent = 'Nenhum volume lógico retornado por vfs.fs.get ou vfs.fs.size neste host.';
      volFragment.append(hint);
    }
    volumesEl.replaceChildren(volFragment);
    panel.hidden = false;
  }
}

export function renderItems(payload) {
  if (!selectedHost || String(payload?.hostid) !== String(selectedHost.hostid)) {
    return;
  }
  currentItems = payload.items || [];
  if (!payload.pending) {
    renderSpecifications(payload.specs || {});
    renderStorage(payload.storage || {});
  }
  setText('#overview-summary', hostLabel(selectedHost) + ' · ' +
    currentItems.length + ' itens disponíveis');
  // Não inferir métricas de rede no frontend; apenas dados validados pelo backend.
  const gauges = payload.gauges || {};
  refreshTrends(String(payload.hostid), gauges);
  renderGauges(gauges);
  renderTrendLines();
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
    network_in: 'Rede RX', network_out: 'Rede TX',
  };
  for (const [kind, info] of Object.entries(diagnostics)) {
    if (info.available || !Object.hasOwn(labels, kind)) continue;
    const line = document.createElement('p');
    line.className = 'coverage-warning';
    line.textContent = labels[kind] + ': ' +
      (info.reason || 'Sem item válido') + ' ' + (info.suggestion || '');
    fragment.append(line);
  }
  container.replaceChildren(fragment);
}
