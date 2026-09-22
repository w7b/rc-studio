// The CSRF token is held here rather than passed around: in the shared deployment it
// belongs to the session, and every writer should send the current one without having
// to know where it came from. It is never persisted — a token that outlives the tab
// would outlive the session it belongs to.
let csrf = '';
let onUnauthorized = null;

export function setCsrf(value) {
  csrf = value || '';
}

export function onSessionLost(handler) {
  onUnauthorized = handler;
}

export async function api(path, options = {}) {
  const response = await fetch(path, {
    cache: 'no-store',
    credentials: 'same-origin',
    ...options,
  });
  if (response.status === 401 && onUnauthorized) {
    // Without this the 2s poll keeps hammering a dead session and the user only ever
    // sees a generic "could not connect".
    onUnauthorized();
    throw new Error('Sessão expirada');
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Não foi possível conectar ao app');
  return data;
}

export const post = (path, data, token) =>
  api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-App-Token': token ?? csrf },
    body: JSON.stringify(data),
  });

export function fileData(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = () => reject(new Error('Não foi possível ler a imagem'));
    reader.readAsDataURL(file);
  });
}
