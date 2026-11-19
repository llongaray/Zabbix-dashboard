/** Gráficos históricos (history.get / trend.get), sem dados fictícios. */
import {requestJSON} from './api.js';
import {$, setMessage, setText, showView} from './state.js';

let currentItem = null;
let graph = null;

export function initializeHistory() {
  $('#days').addEventListener('change', () => {
    if (currentItem) openHistory(currentItem);
  });
}

export async function openHistory(item) {
  currentItem = item;
  showView('history');
  setText('#chart-title', item.name);
  setMessage('#chart-status', 'Carregando histórico...');
  try {
    const data = await requestJSON('/api/history/' + encodeURIComponent(item.itemid) +
      '?days=' + $('#days').value + '&value_type=' + item.value_type);
    if (graph) {
      graph.destroy();
      graph = null;
    }
    if (!data.points || !data.points.length) {
      setMessage('#chart-status', 'Sem dados retidos pelo Zabbix neste período.');
      return;
    }
    if (typeof window.Chart === 'undefined') {
      setMessage('#chart-status', 'Chart.js não carregou. Verifique o acesso à CDN.', true);
      return;
    }
    const ctx = $('#chart');
    graph = new window.Chart(ctx, {
      type: 'line',
      data: {
        labels: data.points.map(point =>
          new Date(Number(point.clock) * 1000).toLocaleString('pt-BR')),
        datasets: [{
          label: item.name,
          data: data.points.map(point => Number(point.value_avg ?? point.value)),
          borderColor: '#a96bff',
          backgroundColor: 'rgba(169,107,255,.13)',
          fill: true,
          tension: .24,
          pointRadius: 0,
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {legend: {labels: {color: '#dfe5ff'}}},
        scales: {
          x: {ticks: {color: '#8997bc', maxTicksLimit: 8}, grid: {color: '#2a3554'}},
          y: {ticks: {color: '#8997bc'}, grid: {color: '#2a3554'}},
        },
      },
    });
    setMessage('#chart-status', data.total + ' pontos históricos; ' +
      data.points.length + ' pontos exibidos · ' + data.source);
  } catch (error) {
    setMessage('#chart-status', error.message, true);
  }
}
