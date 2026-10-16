import React from 'react';
import {
  Database,
  FileText,
  FolderOpen,
  Gauge,
  Images,
  LogOut,
  Megaphone,
  Network,
  Plus,
  ShieldCheck,
  SlidersHorizontal,
  Store,
  UserCog,
  ChevronRight,
} from '../shared/icons.js';
import { PAGE_MODULE, STUDIO_MENU, STUDIO_ROUTES } from '../shared/navigation/routes.js';
import Tooltip from '../shared/components/Tooltip.jsx';

const icons = {
  consultations: Megaphone,
  create: Plus,
  history: FolderOpen,
  gallery: Images,
  references: Images,
  erp: Database,
  ads: Megaphone,
  config: SlidersHorizontal,
  account: UserCog,
  security: ShieldCheck,
  store: Store,
  brandkit: FileText,
  usage: Gauge,
  logs: Network,
  admin: ShieldCheck,
};

export default function StudioSidebar({
  page,
  session,
  open,
  groups,
  onToggleGroup,
  onNavigate,
  connected,
  count,
  onSignedOut,
}) {
  const visible = STUDIO_MENU.filter(
    ({ id, sessionOnly, ownerOnly }) =>
      (!sessionOnly || session) &&
      (!ownerOnly || session?.role === 'OWNER') &&
      session?.modules?.[PAGE_MODULE[id]] !== false
  );
  const parents = new Set(visible.map(({ under }) => under).filter(Boolean));
  const active = page === 'result' ? 'history' : page;
  return (
    <aside id="studio-navigation" inert={!open} className={`sidebar${open ? ' is-open' : ''}`}>
      <a
        className="wordmark"
        href={STUDIO_ROUTES.create}
        onClick={(event) => {
          if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
          event.preventDefault();
          onNavigate('create');
        }}
      >
        <span>
          Studio<strong>AI</strong>
        </span>
      </a>
      <nav aria-label="Módulos do Studio">
        {visible
          .filter(({ under }) => !under || groups.includes(under))
          .map(({ id, label, under }) => {
            const Icon = icons[id];
            const parent = parents.has(id);
            return (
              <div
                key={id}
                className={`studio-nav-row flex min-w-0 items-center ${active === id ? 'is-active' : ''} ${under ? 'is-child' : ''}`}
              >
                <a
                  href={STUDIO_ROUTES[id]}
                  aria-current={active === id ? 'page' : undefined}
                  className={`min-w-0 flex-1 ${active === id ? 'active' : ''} ${under ? 'nav-child' : ''}`}
                  onClick={(event) => {
                    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
                    event.preventDefault();
                    if (parent && !groups.includes(id)) onToggleGroup(id);
                    onNavigate(id, parent);
                  }}
                >
                  <Icon size={18} className="shrink-0" aria-hidden="true" />
                  <span className="min-w-0 truncate">{label}</span>
                  {id === 'history' && <small>{count}</small>}
                </a>
                {parent && (
                  <Tooltip text={`${groups.includes(id) ? 'Recolher' : 'Expandir'} ${label}`}>
                    <button
                      type="button"
                      className={`studio-nav-caret${groups.includes(id) ? ' is-open' : ''}`}
                      aria-label={`${groups.includes(id) ? 'Recolher' : 'Expandir'} ${label}`}
                      aria-expanded={groups.includes(id)}
                      onClick={() => onToggleGroup(id)}
                    >
                      <ChevronRight size={15} aria-hidden="true" />
                    </button>
                  </Tooltip>
                )}
              </div>
            );
          })}
      </nav>
      <div className="sidebar-account">
        <div className="sidebar-bottom" role="status">
          <span className={`connection-dot ${connected ? 'online' : ''}`} aria-hidden="true" />
          {connected ? 'Conectado ao servidor' : 'Conectando ao servidor…'}
        </div>
        {session && onSignedOut && (
          <button className="logout-button" type="button" onClick={onSignedOut}>
            <LogOut size={16} aria-hidden="true" />
            Sair da conta
          </button>
        )}
      </div>
    </aside>
  );
}
