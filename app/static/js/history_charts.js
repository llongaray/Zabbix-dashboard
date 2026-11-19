/** Visualização das séries temporais de cada recurso, com regras por unidade. */
import {setMessage, setText} from './state.js';

const chartObjects = new Map();
const COLORS = {
  cpu: '#a970ff', memory: '#5dbbe9', gpu: '#ed7dc5',
  network_in: '#6bc2ed', network_out: '#ae79ff',
};
const SEVERITY = [
  {level: 80, name: 'Atenção', color: '#e9b963'},
  {level: 90, name: 'Crítico', color: '#f48083'},
  {level: 100, name: 'Máximo', color: '#e6506d'},
];

function severity(pct) {
  if (pct === null || !Number.isFinite(pct)) return ['Sem limite', ''];
  if (pct >= 100) return ['Máximo', 'maximum'];
  if (pct >= 90) return ['Crítico', 'critical'];
  if (pct >= 80) return ['Atenção', 'warning'];
  return ['Normal', 'normal'];
}

function normalizedSeries(rows) {
  return (rows || []).map(series => ({
    name: String(series.name || ''),
    points: (series.points || []).filter(point =>
      Number.isFinite(Number(point.value)) &&
      Number.isFinite(Number(point.clock)))
      .map(point => ({
        x: Number(point.clock) * 1000,
        y: Number(point.value),
      })).sort((a, b) => a.x - b.x),
  }));
}

export function clearHistoryCharts() {
  for (const chart of chartObjects.values()) chart.destroy();
  chartObjects.clear();
}

export function renderMetric(kind, data, sourceLabel) {
  const target = document.getElementById('chart-' + kind);
  if (!target) return;
  const series = normalizedSeries(data.series);
  const actual = series.filter(row => row.points.length);
  if (!actual.length) {
    // Erro ou ausência de retenção oficial não apaga a prévia persistida.
    if (!chartObjects.has(kind)) setText('#history-badge-' + kind, 'Sem dados');
    setMessage('#history-message-' + kind,
      data.message || 'Sem série oficial para este período; cache local preservado.');
    return;
  }
  chartObjects.get(kind)?.destroy();
  chartObjects.delete(kind);
  if (typeof window.Chart === 'undefined') {
    setMessage('#history-message-' + kind, 'Chart.js não foi carregado.', true);
    return;
  }
  const xValues = actual.flatMap(row => row.points.map(p => p.x));
  const minX = Math.min(...xValues);
  const maxX = Math.max(...xValues);
  const percent = kind !== 'network';
  const capacity = Number(data.capacity_mbps);
  const validCapacity = kind === 'network' && capacity > 0;
  const thresholds = percent ? SEVERITY.map(row =>
    ({...row, value: row.level})) : validCapacity ?
      SEVERITY.map(row => ({...row, value: capacity * row.level / 100})) : [];
  const datasets = actual.map((row, index) => ({
    label: row.name === 'network_in' ? 'Recebido (RX)' :
      row.name === 'network_out' ? 'Enviado (TX)' : data.title || kind.toUpperCase(),
    data: row.points,
    parsing: false,
    borderColor: COLORS[row.name] || COLORS[kind] || '#a970ff',
    backgroundColor: 'transparent',
    borderWidth: 2,
    pointRadius: 0,
    tension: .12,
  }));
  // As linhas de limiar não são inventadas quando não sabemos a capacidade.
  for (const row of thresholds) {
    datasets.push({
      label: row.name + ' · ' + row.level + '%',
      data: [{x: minX, y: row.value}, {x: Math.max(minX + 1, maxX), y: row.value}],
      parsing: false,
      borderColor: row.color,
      borderDash: [5, 5],
      borderWidth: 1,
      pointRadius: 0,
      tension: 0,
    });
  }
  let last = null;
  for (const line of actual) {
    const candidate = line.points[line.points.length - 1];
    if (candidate && (last === null || candidate.y > last)) last = candidate.y;
  }
  const currentPct = percent ? last : validCapacity && last !== null ?
    last / capacity * 100 : null;
  const [label, className] = severity(currentPct);
  const badge = document.getElementById('history-badge-' + kind);
  badge.textContent = label;
  badge.className = 'metric-status ' + className;
  const chart = new window.Chart(target, {
    type: 'line',
    data: {datasets},
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      interaction: {intersect: false, mode: 'nearest'},
      plugins: {
        legend: {
          labels: {color: '#d5def6', boxWidth: 18, font: {size: 10}},
        },
        tooltip: {
          callbacks: {
            title: items => items.length ?
              new Date(items[0].parsed.x).toLocaleString('pt-BR') : '',
            label: item => item.dataset.label + ': ' +
              Number(item.parsed.y).toLocaleString('pt-BR', {
                maximumFractionDigits: 3,
              }) + (percent ? '%' : ' Mbps'),
          },
        },
      },
      scales: {
        x: {
          type: 'linear',
          ticks: {color: '#94a2ca', maxTicksLimit: 6,
            callback: value => {
              const date = new Date(Number(value));
              return maxX - minX <= 2 * 86400000 ?
                date.toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'}) :
                date.toLocaleDateString('pt-BR');
            }},
          grid: {color: '#2e3657'},
        },
        y: {
          min: 0,
          max: percent ? 100 : undefined,
          ticks: {color: '#94a2ca', maxTicksLimit: 6},
          grid: {color: '#2e3657'},
        },
      },
    },
  });
  chartObjects.set(kind, chart);
  const count = actual.reduce((total, row) => total + row.points.length, 0);
  setMessage('#history-message-' + kind,
    count + ' amostras · ' + sourceLabel +
    (kind === 'network' && !validCapacity ?
      ' · limites percentuais indisponíveis sem velocidade da interface' : ''));
}

export function renderLocal(kind, local) {
  const kinds = kind === 'network' ? ['network_in', 'network_out'] : [kind];
  const series = kinds.map(name => ({
    name, points: local?.[name] || [],
  })).filter(row => row.points.length);
  if (!series.length) return false;
  renderMetric(kind, {
    kind, title: kind === 'network' ? 'Rede RX/TX' : kind.toUpperCase(),
    series,
    message: 'Sem dados em cache.',
  }, 'cache PostgreSQL');
  return true;
}
