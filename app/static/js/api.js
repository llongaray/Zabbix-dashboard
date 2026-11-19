/** Cliente HTTP do Flask. Falha na API Zabbix nunca encerra a sessão local. */
export class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

export async function requestJSON(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {credentials: 'same-origin', cache: 'no-store', ...options});
  } catch (error) {
    throw new ApiError('Não foi possível acessar o backend Flask.', 0, 'NETWORK');
  }
  const text = await response.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new ApiError('Servidor retornou HTML ou conteúdo inesperado (HTTP ' +
      response.status + ').', response.status, 'INVALID_JSON');
  }
  if (!response.ok) {
    // Somente Flask pode indicar SESSION_EXPIRED; HTTP 401 do Zabbix vira 502.
    throw new ApiError(data.error || 'Falha HTTP ' + response.status,
      response.status, data.code || 'HTTP_ERROR');
  }
  return data;
}

export function postJSON(path, body = {}) {
  return requestJSON(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
}
