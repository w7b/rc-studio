import { requestJson, postJson, setCsrf } from './http.js';

export const accountService = {
  updateDetails: ({ name, email, phone }) =>
    postJson('/api/account', { name, email: email.trim(), phone: phone.trim() }),
  async changePassword(payload) {
    const result = await postJson('/api/account/password', payload);
    setCsrf(result.csrf);
    return result;
  },
  getStore: (options) => requestJson('/api/store', options),
  updateStore: (payload) => postJson('/api/store', payload),
};
