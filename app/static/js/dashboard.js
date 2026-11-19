/** Orquestrador do frontend; lógica distribuída entre módulos reutilizáveis. */
import {requestJSON} from './api.js';
import {initializeNavigation, $, setMessage} from './state.js';
import {initializeHistory, openHistory} from './history.js';
import {initializeHosts, renderSnapshot, renderItems, showHostError} from './hosts.js';
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
    onConnected: () => requestRefresh(),
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

initialize();
