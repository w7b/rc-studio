import { requestJson, postJson } from './http.js';

export const mediaService = {
  list: (options) => requestJson('/api/media', options),
  remove: (id, source = 'media', token) =>
    postJson(`/api/${encodeURIComponent(source)}/${encodeURIComponent(id)}/delete`, {}, token),
};
