import { requestJson, postJson, requestBlob } from './http.js';

export const referenceService = {
  list: (options) => requestJson('/api/references', options),
  create: (payload, token) => postJson('/api/references', payload, token),
  getEditorOptions: (options) => requestJson('/api/references/editor-options', options),
  edit: (payload, token) => postJson('/api/references/edit', payload, token),
  downloadUrl: (id) => `/api/references/${encodeURIComponent(id)}/download`,
  async getCampaignDraft(item, options) {
    const blob = await requestBlob(item.url, 'Não foi possível carregar a referência', options);
    return {
      id: 'reference-' + item.id,
      [item.kind === 'product' ? 'photo' : 'reference']: new File(
        [blob],
        item.title + '.' + item.extension,
        { type: blob.type }
      ),
    };
  },
};
