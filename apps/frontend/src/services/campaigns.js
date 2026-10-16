import { requestJson, postJson } from './http.js';
import { imageFile } from './files.js';

const runPath = (id) => `/api/runs/${encodeURIComponent(id)}`;

export const campaignService = {
  list: (options) => requestJson('/api/runs', options),
  getFormats: (options) => requestJson('/api/formats', options),
  create: (payload, token) => postJson('/api/runs', payload, token),
  assistBrief: (payload, token) => postJson('/api/brief-assist', payload, token),
  generateImage: (id, payload = {}, token) => postJson(`${runPath(id)}/image`, payload, token),
  retry: (id, token) => postJson(`${runPath(id)}/retry`, {}, token),
  rename: (id, title, token) => postJson(`${runPath(id)}/rename`, { title }, token),
  remove: (id, token) => postJson(`${runPath(id)}/delete`, {}, token),
  async getDraft(id, options) {
    const data = await requestJson(`${runPath(id)}/draft`, options);
    return {
      ...data,
      id,
      photo: imageFile(data.upload, 'produto'),
      reference: imageFile(data.reference_upload, 'referencia'),
    };
  },
  fileUrl: (id, name) => `${runPath(id)}/files/${encodeURIComponent(name)}`,
};
