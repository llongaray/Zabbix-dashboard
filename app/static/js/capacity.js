import {requestJSON} from './api.js';
import {$, setMessage, setText, onView} from './state.js';

const format = new Intl.NumberFormat('pt-BR', {maximumFractionDigits: 1});
const gib = value => value == null ? '—' : format.format(value) + ' GiB';

function comparison(windows) {
  if (!windows) return '—';
  return windows.map(window => window.peak == null ? 'Sem dados' :
    format.format(window.peak) + '% (' + format.format(window.coverage) + '% cobertura)').join(' / ');
}

function render(report) {
  const table = $('#capacity-rows');
  const rows = report.hosts.map(host => {
    const row = document.createElement('tr');
    const peak = host.peak_pct == null ? '—' :
      format.format(host.peak_pct) + '%' + (host.peak_gib == null ? '' : ' · ' + gib(host.peak_gib));
    const columns = [host.name, gib(host.total_gib), peak,
      format.format(host.coverage_pct) + '%', gib(host.releasable_gib || null),
      gib(host.needed_gib || null), host.status,
      ...['cpu', 'memory', 'disk'].map(kind => comparison(host.metrics?.[kind]))];
    columns.forEach((value, index) => {
      const cell = document.createElement(index === 0 ? 'th' : 'td');
      if (index === 0) cell.scope = 'row';
      cell.textContent = value;
      row.append(cell);
    });
    return row;
  });
  table.replaceChildren(...rows);

  const suggestions = $('#capacity-suggestions');
  suggestions.replaceChildren();
  if (!report.suggestions.length) {
    suggestions.textContent = 'Nenhum remanejamento sugerido com os dados e critérios atuais.';
  }
  for (const proposal of report.suggestions) {
    const line = document.createElement('div');
    line.className = 'capacity-suggestion';
    const amount = document.createElement('span');
    amount.className = 'siga-badge siga-badge--primary';
    amount.textContent = gib(proposal.gib);
    const path = document.createElement('span');
    path.textContent = proposal.from + ' → ' + proposal.to;
    line.append(amount, path);
    suggestions.append(line);
  }
  setText('#capacity-policy', 'Últimos ' + report.days + ' dias completos de amostras horárias, com ' +
    report.min_coverage + '% de cobertura mínima e RAM total histórica confirmada. ' +
    'A estimativa deixa ao menos ' + gib(report.min_donor_gib) + ' no doador e limita seu pico projetado a ' +
    report.donor_limit + '%. Prioriza servidores com pico de ' + report.receiver_threshold +
    '% ou mais, com meta de ' + report.receiver_target + '%.');
}

export function initializeCapacity() {
  const refresh = $('#capacity-refresh');
  let loaded = false;
  async function load() {
    if (refresh.disabled) return;
    refresh.disabled = true;
    setMessage('#capacity-status', 'Consultando os máximos horários no Zabbix…');
    try {
      const report = await requestJSON('/api/capacity');
      render(report);
      loaded = true;
      setMessage('#capacity-status', report.hosts.length ?
        'Análise atualizada às ' + new Date().toLocaleTimeString('pt-BR') :
        'Aguardando servidores com dados coletados.');
    } catch (error) {
      setMessage('#capacity-status', error.message, true);
    } finally {
      refresh.disabled = false;
    }
  }
  refresh.addEventListener('click', load);
  onView('capacity', () => { if (!loaded) void load(); });
}
