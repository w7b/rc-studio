// Session CSRF belongs to the transport and is never persisted beyond this tab.
let csrf = '';
let onUnauthorized = null;

export function setCsrf(value) {
  csrf = value || '';
}

export function onSessionLost(handler) {
  onUnauthorized = handler;
}

export async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    cache: 'no-store',
    credentials: 'same-origin',
    ...options,
  });
  if (response.status === 401 && onUnauthorized) {
    onUnauthorized();
    throw new Error('Sessão expirada');
  }
  const fallback = `Não foi possível conectar ao app (HTTP ${response.status})`;
  let data;
  try {
    data = await response.json();
  } catch (error) {
    if (response.ok || error.name === 'AbortError') throw error;
    throw new Error(fallback);
  }
  if (!response.ok) {
    throw new Error(typeof data?.error === 'string' && data.error ? data.error : fallback);
  }
  return data;
}

export function postJson(path, data, token, options = {}) {
  return requestJson(path, {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-App-Token': token ?? csrf },
    body: JSON.stringify(data),
  });
}

// Asset reads retain normal browser caching and do not carry a CSRF token.
export async function requestBlob(url, errorMessage, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(errorMessage);
  return response.blob();
}
