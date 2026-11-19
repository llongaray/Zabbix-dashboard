/** Tela de configuração de token, diagnóstico e catálogo de API. */
import {postJSON, requestJSON} from './api.js';
import { $, setMessage, setText } from './state.js';

let refresh = () => {};
let methods = [];

export function initializeSettings(options = {}) {
  refresh = options.refresh || refresh;
  $('#settings-form').addEventListener('submit', handleSave);
  $('#test-token').addEventListener('click', testSaved);
  $('#check-methods').addEventListener('click', checkMethods);
}

export async function loadConfiguration() {
  try {
    const [config, catalog] = await Promise.all([
      requestJSON('/api/config'),
      requestJSON('/api/catalog'),
    ]);
    setText('#endpoint', catalog.endpoint);
    setText('#poll-interval', config.poll_interval + ' segundos');
    setText('#config-token', config.token_configured ? 'Cadastrado' : 'Pendente');
    $('#test-token').disabled = !config.token_configured;
    methods = catalog.methods || [];
    renderCatalog({});
    setMessage('#settings-status', config.token_configured ?
      'Token cadastrado. Teste a conexão ou aguarde a atualização por WebSocket.' :
      'Cadastre seu token nativo do Zabbix para começar.');
    return config;
  } catch (error) {
    setMessage('#settings-status', error.message, true);
    return {token_configured: false};
  }
}

async function handleSave(event) {
  event.preventDefault();
  const button = $('#save-token');
  const token = $('#token').value.trim();
  if (!token) {
    setMessage('#settings-status', 'Informe o token para validar.', true);
    return;
  }
  button.disabled = true;
  setMessage('#settings-status', 'Validando token via host.get no Zabbix...');
  try {
    // O token é enviado somente ao backend Flask via HTTPS/local.
    const result = await postJSON('/api/config', {token});
    $('#token').value = '';
    setText('#config-token', 'Validado');
    setText('#config-latency', result.validation.latency_ms + ' ms');
    setText('#config-version', result.validation.version || 'Indisponível');
    $('#test-token').disabled = false;
    setMessage('#settings-status', 'Token validado e salvo criptografado no PostgreSQL.');
    refresh();
  } catch (error) {
    setMessage('#settings-status', 'Não foi possível salvar: ' + error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function testSaved() {
  const button = $('#test-token');
  button.disabled = true;
  setMessage('#settings-status', 'Testando token persistido...');
  try {
    const data = await postJSON('/api/config/test');
    setText('#config-version', data.version);
    setText('#config-latency', data.latency_ms + ' ms');
    setText('#config-token', 'Validado');
    setMessage('#settings-status', data.host_accessible ?
      'Conexão confirmada. O token tem acesso a hosts.' :
      'Token validado, mas nenhum host foi retornado pela permissão atual.');
    refresh();
  } catch (error) {
    setMessage('#settings-status', error.message, true);
  } finally {
    button.disabled = false;
  }
}

function renderCatalog(probe) {
  const tbody = $('#method-body');
  tbody.replaceChildren();
  for (const method of methods) {
    const result = probe[method.method];
    const row = document.createElement('tr');
    const id = document.createElement('td');
    id.textContent = method.method;
    const purpose = document.createElement('td');
    purpose.textContent = method.description;
    const status = document.createElement('td');
    const chip = document.createElement('span');
    chip.className = 'method-status ' + (result?.status || '');
    chip.textContent = result?.status === 'ok' ? 'Permitido' :
      result?.status === 'error' ? 'Negado / erro' :
      method.method === 'apiinfo.version' ? 'Público' :
      ['history.get', 'trend.get'].includes(method.method) ?
        'Requer item numérico' : 'Não testado';
    if (result?.message) chip.title = result.message;
    status.append(chip);
    const latency = document.createElement('td');
    latency.textContent = result?.latency_ms == null ? '—' :
      result.latency_ms + ' ms';
    row.append(id, purpose, status, latency);
    tbody.append(row);
  }
}

async function checkMethods() {
  const button = $('#check-methods');
  button.disabled = true;
  setMessage('#methods-status', 'Consultando permissões de leitura na API Zabbix...');
  try {
    const data = await postJSON('/api/catalog/check');
    renderCatalog(data.results || {});
    const allowed = Object.values(data.results || {})
      .filter(row => row.status === 'ok').length;
    setMessage('#methods-status', allowed + ' métodos de leitura testados com sucesso.');
  } catch (error) {
    setMessage('#methods-status', error.message, true);
  } finally {
    button.disabled = false;
  }
}

export function onTokenValidated(report) {
  setText('#config-token', 'Validado');
  setText('#config-latency', report.latency_ms + ' ms');
  setText('#config-version', report.version || 'Indisponível');
}

export function showIntegrationStatus(payload) {
  const connected = !!payload.connected;
  setText('#connection', connected ? '● Zabbix conectado' : '● Conexão indisponível');
  setMessage('#integration-message', payload.message || '', !connected);
}

export function showWebSocketStatus(text) {
  setText('#ws-connection', text);
  setText('#config-ws', text.replace('WebSocket: ', ''));
}
