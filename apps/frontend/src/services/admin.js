import { requestJson, postJson } from './http.js';

export const adminService = {
  getOverview: (options) => requestJson('/api/admin/overview', options),
  getMetrics: (options) => requestJson('/api/admin/metrics', options),
  getModelKeys: (tenantId, options) =>
    requestJson(`/api/admin/tenants/model-keys?tenant_id=${encodeURIComponent(tenantId)}`, options),
  createTenant: (payload) =>
    postJson('/api/admin/tenants', { ...payload, root_path: payload.root_path.trim() || null }),
  setTenantStatus: (payload) => postJson('/api/admin/tenants/status', payload),
  createInvite: (payload) => postJson('/api/admin/invites', payload),
  saveModelKeys: (payload) => postJson('/api/admin/tenants/model-keys', payload),
  setModule: (payload) => postJson('/api/admin/tenants/modules', payload),
  validateMetaAds: (payload) => postJson('/api/admin/tenants/meta-ads/validate', payload),
  updateMembership: (payload) => postJson('/api/admin/memberships', payload),
  revokeMembership: (payload) => postJson('/api/admin/memberships/revoke', payload),
};
