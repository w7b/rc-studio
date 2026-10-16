import { requestJson, postJson } from './http.js';

export const brandKitService = {
  get: (options) => requestJson('/api/brandkit', options),
  seed: () => postJson('/api/brandkit/seed', {}),
  saveFile: (name, content) => postJson('/api/brandkit', { name, content }),
};
