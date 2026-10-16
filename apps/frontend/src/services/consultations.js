import { postJson } from './http.js';

export const consultationService = {
  create: (payload, token) => postJson('/api/consultations', payload, token),
};
