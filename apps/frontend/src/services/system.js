import { requestJson } from './http.js';

export const systemService = {
  getUsage: (options) => requestJson('/api/usage', options),
  getLogs: (options) => requestJson('/api/logs', options),
};
