/** Cliente Socket.IO autenticado: fallback HTTP quando transporte não disponível. */
import {requestJSON} from './api.js';
import {showWebSocketStatus} from './settings.js';

export function connectStream(handlers) {
  let socket = null;
  let polling = null;
  const fallbackInterval = 30000;

  async function pollOnce() {
    try {
      const data = await requestJSON('/api/snapshot');
      handlers.onSnapshot(data);
      handlers.onIntegration({connected: true, message: 'Consulta HTTP ativa.'});
    } catch (error) {
      handlers.onIntegration({connected: false, message: error.message});
    }
  }

  function enableFallback() {
    if (polling) return;
    showWebSocketStatus('Fallback HTTP');
    polling = setInterval(pollOnce, fallbackInterval);
  }

  function disableFallback() {
    if (!polling) return;
    clearInterval(polling);
    polling = null;
  }

  if (typeof window.io !== 'undefined') {
    socket = window.io({
      transports: ['websocket', 'polling'],
      tryAllTransports: true,
      reconnection: true,
      reconnectionDelayMax: 10000,
      timeout: 15000,
    });
    socket.on('connect', () => {
      showWebSocketStatus('WebSocket: conectado');
      disableFallback();
      handlers.onConnected?.();
    });
    socket.on('disconnect', () => enableFallback());
    socket.on('connect_error', () => enableFallback());
    socket.on('snapshot', handlers.onSnapshot);
    socket.on('host_items', handlers.onHostItems);
    socket.on('host_error', handlers.onHostError);
    socket.on('integration_status', handlers.onIntegration);
    socket.on('token_validated', handlers.onTokenValidated);
  } else {
    enableFallback();
  }

  return {
    get connected() { return !!socket?.connected; },
    refresh() {
      if (socket?.connected) socket.emit('refresh');
      else pollOnce();
    },
    watchHost(hostid) {
      if (socket?.connected) socket.emit('watch_host', {hostid});
    },
    close() {
      disableFallback();
      socket?.disconnect();
    },
  };
}
