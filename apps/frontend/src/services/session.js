import { requestJson, postJson } from './http.js';

export { setCsrf, onSessionLost } from './http.js';

export const sessionService = {
  getConfig: (options) => requestJson('/api/config', options),
  getSession: (options) => requestJson('/api/session', options),
  signIn: ({ email, password }) => postJson('/api/login', { email: email.trim(), password }),
  signOut: () => postJson('/api/logout', {}),
  acceptInvite: ({ token, email, password, name }) =>
    postJson('/api/invites/accept', { token, email: email.trim(), password, name: name.trim() }),
  providerUrl: (provider) => `/api/auth/${encodeURIComponent(provider)}`,
};
