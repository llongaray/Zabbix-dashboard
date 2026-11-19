/** Orquestrador do frontend; lógica distribuída entre módulos reutilizáveis. */
import {requestJSON} from './api.js';
import {initializeNavigation, $, setMessage} from './state.js';
import {initializeHistory, openHistory} from './history.js';
import {initializeHosts, getSelectedHostId, renderSnapshot, renderItems, showHostError} from './hosts.js';
import {initializeSettings, loadConfiguration, onTokenValidated,
  showIntegrationStatus} from './settings.js';
import {connectStream} from './socket.js';

let stream = null;

async function loadOnce() {
  try {
    const payload = await requestJSON('/api/snapshot');
    renderSnapshot(payload);
    if (payload.version) document.querySelector('#config-version').textContent = payload.version;
    showIntegrationStatus({connected: true, message: 'Integração respondendo.'});
  } catch (error) {
    showIntegrationStatus({connected: false, message: error.message});
    setMessage('#overview-status', error.message, true);
  }
}

function requestRefresh() {
  if (stream) stream.refresh();
  else loadOnce();
}

async function initialize() {
  initializeNavigation();
  initializeHistory();
  initializeHosts({
    onHistory: openHistory,
    onWatch: hostid => stream?.watchHost(hostid),
  });
  initializeSettings({refresh: requestRefresh});

  const config = await loadConfiguration();
  stream = connectStream({
    onConnected: () => {
      const host = getSelectedHostId();
      if (host) stream?.watchHost(String(host));
      requestRefresh();
    },
    onSnapshot: payload => {
      renderSnapshot(payload);
      if (payload.version) {
        document.querySelector('#config-version').textContent = payload.version;
      }
    },
    onHostItems: renderItems,
    onHostError: showHostError,
    onIntegration: showIntegrationStatus,
    onTokenValidated,
  });

  $('#refresh').addEventListener('click', requestRefresh);
  if (config.token_configured) await loadOnce();
  else showIntegrationStatus({
    connected: false,
    message: 'Cadastre somente o API Token na aba Configurações.',
  });
}

initialize().catch(error => {
  // Um erro isolado de DOM/API deve permanecer visível, nunca ocultar o defeito.
  const message = 'Falha ao inicializar o dashboard: ' + (error?.message || error);
  console.error(message, error);
  setMessage('#settings-status', message, true);
  setMessage('#overview-status', message, true);
  const connection = $('#connection');
  if (connection) connection.textContent = '● Erro na inicialização';
});
