// URLs are the source of truth, including refresh and browser back/forward.
export const STUDIO_ROUTES = {
  consultations: '/studio/meta-ads/consultations',
  create: '/studio',
  history: '/studio/campaigns',
  gallery: '/studio/library',
  references: '/studio/library/references',
  erp: '/studio/erp',
  ads: '/studio/meta-ads',
  config: '/studio/settings',
  account: '/studio/settings/account',
  security: '/studio/settings/security',
  store: '/studio/settings/store',
  brandkit: '/studio/settings/brand-kit',
  usage: '/studio/agentes',
  logs: '/studio/logs',
  admin: '/admin',
};

// `under` nests an item beneath its parent in the sidebar. The consultancy plans paid
// media and references are Library material, so each sits with the module it belongs to
// rather than competing with it for a top-level slot.
export const STUDIO_MENU = [
  { id: 'create', label: 'Criar campanha' },
  { id: 'history', label: 'Campanhas' },
  { id: 'gallery', label: 'Biblioteca' },
  { id: 'references', label: 'Referências', under: 'gallery' },
  { id: 'erp', label: 'ERP e relatórios' },
  { id: 'ads', label: 'Meta Ads' },
  { id: 'consultations', label: 'Consultoria de marketing', under: 'ads' },
  { id: 'config', label: 'Configurações', sessionOnly: true },
  { id: 'account', label: 'Dados pessoais', under: 'config', sessionOnly: true },
  { id: 'security', label: 'Segurança', under: 'config', sessionOnly: true },
  { id: 'store', label: 'Dados da loja', under: 'config', sessionOnly: true },
  { id: 'brandkit', label: 'Brand Kit', under: 'config', sessionOnly: true },
  { id: 'usage', label: 'Consumo dos agentes', ownerOnly: true },
  { id: 'logs', label: 'Logs', ownerOnly: true },
  { id: 'admin', label: 'Administração', ownerOnly: true },
];

export const PAGE_MODULE = {
  // Grouped with the module each one belongs to: the consultancy plans paid media, and
  // references are Library material. Turning off Meta Ads takes the consultancy with it.
  consultations: 'meta_ads',
  create: 'campaigns',
  history: 'campaigns',
  result: 'campaigns',
  gallery: 'art_lib',
  references: 'art_lib',
  erp: 'erp',
  ads: 'meta_ads',
  usage: 'agents',
  logs: 'logs',
};

export function campaignUrl(id) {
  return `${STUDIO_ROUTES.history}?run=${encodeURIComponent(id)}`;
}

export function breadcrumbsFor(page) {
  if (page === 'result')
    return [
      { id: 'history', label: 'Campanhas' },
      { id: 'result', label: 'Resultados' },
    ];
  const item = STUDIO_MENU.find((entry) => entry.id === page);
  if (!item) return [];
  const parent = STUDIO_MENU.find((entry) => entry.id === item.under);
  return [
    ...(parent ? [parent] : []),
    { ...item, label: page === 'create' ? 'Nova campanha' : item.label },
  ];
}

const LEGACY_ROUTES = {
  '/studio/campaings': 'history',
  '/studio/art-lib': 'gallery',
  '/studio/references': 'references',
  '/studio/consultoria': 'consultations',
  '/studio/config': 'brandkit',
  '/studio/account': 'account',
};

export function pageFor(route) {
  const [path, query = ''] = route.split('?');
  const page = Object.keys(STUDIO_ROUTES).find((key) => STUDIO_ROUTES[key] === path);
  return page === 'history' && new URLSearchParams(query).has('run') ? 'result' : page;
}

export function routeRedirect(route, status, role, modules = {}) {
  if (!['anonymous', 'ready', 'standalone'].includes(status)) return null;
  const [raw, query] = route.split('?');
  const path = raw.replace(/\/+$/, '') || '/';
  if (path !== raw) return path + (query ? `?${query}` : '');
  if (['/', '/home', '/convite'].includes(path)) return null;
  if (path === '/login') return status === 'anonymous' ? null : '/studio';
  if (status === 'anonymous') return '/';
  if (LEGACY_ROUTES[path]) return STUDIO_ROUTES[LEGACY_ROUTES[path]] + (query ? `?${query}` : '');
  const page = pageFor(route);
  if (!page) return '/home';
  if (['admin', 'usage', 'logs'].includes(page) && role !== 'OWNER') return '/home';
  if (modules[PAGE_MODULE[page]] === false) return STUDIO_ROUTES.account;
  return null;
}
