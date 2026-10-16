import { requestJson, postJson } from './http.js';

export const integrationService = {
  list: (options) => requestJson('/api/integrations', options),
  save: (module, values) => postJson('/api/integrations', { module, values }),
  validateMetaAds: () => postJson('/api/integrations/meta-ads/validate', {}),
};
