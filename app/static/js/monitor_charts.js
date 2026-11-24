import {$} from './state.js';

const severities = ['Não classificada', 'Informação', 'Atenção', 'Média', 'Alta', 'Desastre'];
const tones = ['neutral', 'info', 'warning', 'warning', 'danger', 'danger'];

export function bars(selector, rows, empty = 'Sem dados disponíveis.') {
  const chart = $(selector);
  const maximum = Math.max(1, ...rows.map(row => row[1]));
  if (!rows.length) {
    chart.textContent = empty;
    return;
  }
  chart.replaceChildren(...rows.map(([label, value, tone]) => {
    const line = document.createElement('div');
    line.className = 'bar-line';
    const caption = document.createElement('span');
    caption.textContent = label;
    const track = document.createElement('span');
    track.className = 'bar-track';
    track.setAttribute('aria-hidden', 'true');
    const fill = document.createElement('i');
    fill.dataset.tone = tone || 'primary';
    fill.style.width = (100 * value / maximum) + '%';
    track.append(fill);
    const count = document.createElement('strong');
    count.textContent = value;
    line.append(caption, track, count);
    return line;
  }));
}

export function dayBuckets(rows) {
  const days = new Map();
  for (const row of rows) {
    const stamp = Number(row.opened_at ?? row.clock);
    if (!Number.isFinite(stamp) || stamp <= 0) continue;
    const date = new Date(stamp * 1000);
    const day = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
    days.set(day, (days.get(day) || 0) + 1);
  }
  return [...days].sort(([a], [b]) => b - a).slice(0, 7).map(([day, value]) =>
    [new Date(day).toLocaleDateString('pt-BR', {day: '2-digit', month: '2-digit', year: 'numeric'}), value]);
}

export function renderOverviewCharts(snapshot) {
  const hosts = snapshot.hosts || [];
  const problems = snapshot.problems || [];
  const states = [
    ['Online', 'online', 'success'], ['Sem resposta', 'unreachable', 'danger'],
    ['Coleta recente', 'recent', 'info'], ['Coleta atrasada', 'stale', 'warning'],
    ['Desabilitados', 'disabled', 'neutral'], ['Aguardando', 'pending', 'neutral'],
  ];
  const counts = new Map();
  for (const host of hosts) {
    const state = String(host.status) === '1' ? 'disabled' : host.summary?.status || 'pending';
    counts.set(state, (counts.get(state) || 0) + 1);
  }
  bars('#monitor-host-chart', hosts.length ? states.map(([label, state, tone]) =>
    [label, counts.get(state) || 0, tone]) : [], 'Aguardando coleta de servidores.');
  const bySeverity = Array(6).fill(0);
  for (const problem of problems) {
    const severity = Number(problem.severity);
    bySeverity[Number.isInteger(severity) && severity >= 0 && severity <= 5 ? severity : 0]++;
  }
  const empty = snapshot.kpis?.active_problems === 0 ? 'Nenhum problema ativo.' : 'Aguardando coleta de problemas.';
  bars('#monitor-severity-chart', problems.length ? severities.map((label, i) =>
    [label, bySeverity[i], tones[i]]) : [], empty);
  bars('#monitor-age-chart', dayBuckets(problems), problems.length ? 'Ocorrências sem horário disponível.' : empty);
}
