import React, { useEffect, useState } from 'react';
import { FolderOpen, ArrowUpRight, Plus, ChevronRight, Menu, X } from 'lucide-react';
import { api, post } from '../shared/api/client.js';
import { modelLabel } from '../shared/catalog/models.js';
import References from '../features/references/References.jsx';
import Library from '../features/library/Library.jsx';
import CampaignActions from '../features/campaigns/CampaignActions.jsx';
import Feedback from '../shared/components/Feedback.jsx';
import { followSpotlight } from '../shared/components/SpotlightCard.jsx';
import CampaignForm from '../features/campaigns/CampaignForm.jsx';
import CampaignResults from '../features/campaigns/CampaignResults.jsx';
import IntegrationModules from '../features/integrations/IntegrationModules.jsx';
import Consultations from '../features/consultations/Consultations.jsx';
import AgentUsage from '../features/system/AgentUsage.jsx';
import Logs from '../features/logs/Logs.jsx';
import Settings from '../features/config/Settings.jsx';
import StudioSidebar from './StudioSidebar.jsx';
import StudioBreadcrumbs from './StudioBreadcrumbs.jsx';
import Tooltip from '../shared/components/Tooltip.jsx';
import AdminPanel from '../features/admin/AdminPanel.jsx';
import { campaignUrl, pageFor, PAGE_MODULE, STUDIO_ROUTES } from '../shared/navigation/routes.js';

export default function App({
  session = null,
  onSignedOut = null,
  onAccountUpdated = null,
  route = '/studio',
  navigate,
}) {
  const page = pageFor(route);
  const selected = new URLSearchParams(route.split('?')[1] || '').get('run');
  const setPage = (next) => navigate(STUDIO_ROUTES[next] || STUDIO_ROUTES.history);
  const enabled = (module) => session?.modules?.[module] !== false;
  const brandName = session?.tenant?.name || 'Studio';
  const initials = brandName
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0] || '')
    .join('')
    .toUpperCase();
  const [sort, setSort] = useState('newest'),
    [search, setSearch] = useState('');
  // The sidebar collapses behind a hamburger; a parent with children opens on demand.
  const [desktopMenu, setDesktopMenu] = useState(() => matchMedia('(min-width: 1101px)').matches);
  const [menuOpen, setMenuOpen] = useState(() => desktopMenu);
  const [retryNotice, setRetryNotice] = useState(null);
  const [openGroups, setOpenGroups] = useState([]);
  const menuToggle = React.useRef(null);
  const pageContent = React.useRef(null);
  const pinnedOpen = desktopMenu && menuOpen;
  useEffect(() => {
    const query = matchMedia('(min-width: 1101px)');
    const resize = () => {
      setDesktopMenu(query.matches);
      setMenuOpen(query.matches);
    };
    query.addEventListener('change', resize);
    return () => query.removeEventListener('change', resize);
  }, []);
  useEffect(() => {
    if (!menuOpen) return;
    const escape = (event) => {
      if (event.key === 'Escape') {
        setMenuOpen(false);
        menuToggle.current?.focus();
      }
    };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [menuOpen]);
  React.useLayoutEffect(() => {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const animation = pageContent.current?.animate(
      [
        { opacity: 0, transform: 'translateY(6px)' },
        { opacity: 1, transform: 'translateY(0)' },
      ],
      { duration: 180, easing: 'ease-out' }
    );
    return () => animation?.cancel();
  }, [route]);
  const toggleGroup = (id) =>
    setOpenGroups((current) =>
      current.includes(id) ? current.filter((each) => each !== id) : [...current, id]
    );
  const [config, setConfig] = useState(null),
    [runs, setRuns] = useState([]),
    [media, setMedia] = useState([]),
    [active, setActive] = useState(null),
    [serverBusy, setServerBusy] = useState(false),
    [assisting, setAssisting] = useState(false),
    [connected, setConnected] = useState(false),
    [error, setError] = useState(''),
    [draft, setDraft] = useState(null);
  const activeRef = React.useRef(null);
  const busy = !!active || serverBusy || assisting;
  activeRef.current = busy;
  async function refresh() {
    try {
      const [state, assets] = await Promise.all([
        enabled('campaigns') ? api('/api/runs') : Promise.resolve({ runs: [], active_id: null }),
        ['campaigns', 'art_lib', 'references'].some(enabled)
          ? api('/api/media')
          : Promise.resolve([]),
      ]);
      setRuns(state.runs);
      setActive(state.active_id);
      setServerBusy(state.busy ?? !!state.active_id);
      setMedia(assets);
      setConnected(true);
      return assets;
    } catch {
      setConnected(false);
    }
  }
  useEffect(() => {
    let stopped = false,
      timer;
    async function poll() {
      if (stopped) return;
      await refresh();
      // Poll every 2s while busy, 6s while idle, and 15s while the tab is hidden.
      // Hidden tabs keep polling so they can recover current state when revisited.
      if (!stopped)
        timer = setTimeout(poll, document.hidden ? 15000 : activeRef.current ? 2000 : 6000);
    }
    api('/api/config')
      .then(setConfig)
      .catch((e) => setError(e.message));
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [session?.modules]);
  async function create(payload) {
    const result = await post('/api/runs', payload, config.token);
    setActive(result.id);
    navigate(campaignUrl(result.id));
    await refresh();
  }
  async function assist(payload) {
    setAssisting(true);
    try {
      return await post('/api/brief-assist', payload, config.token);
    } finally {
      await refresh();
      setAssisting(false);
    }
  }
  async function consult(payload) {
    setAssisting(true);
    try {
      return await post('/api/consultations', payload, config.token);
    } finally {
      await refresh();
      setAssisting(false);
    }
  }
  async function image(id, payload = {}) {
    await post('/api/runs/' + id + '/image', payload, config.token);
    setActive(id);
    await refresh();
  }
  async function retry(id) {
    const result = await post('/api/runs/' + id + '/retry', {}, config.token);
    setRetryNotice(result.id);
    setActive(result.id);
    navigate(campaignUrl(result.id));
    await refresh();
  }
  async function rename(id, title) {
    await post('/api/runs/' + id + '/rename', { title }, config.token);
    await refresh();
  }
  async function remove(id) {
    await post('/api/runs/' + id + '/delete', {}, config.token);
    if (selected === id) {
      setPage('history');
    }
    await refresh();
  }
  async function edit(id) {
    const data = await api('/api/runs/' + id + '/draft');
    function file(value, name) {
      if (!value) return null;
      const bytes = Uint8Array.from(atob(value), (c) => c.charCodeAt(0));
      const png = bytes[0] === 137;
      return new File([bytes], name + (png ? '.png' : '.jpg'), {
        type: png ? 'image/png' : 'image/jpeg',
      });
    }
    setDraft({
      ...data,
      id,
      photo: file(data.upload, 'produto'),
      reference: file(data.reference_upload, 'referencia'),
    });
    setPage('create');
  }
  const actions = (run) => (
    <CampaignActions
      run={run}
      busy={busy || !connected || !config}
      onRetry={retry}
      onDelete={remove}
      onEdit={edit}
      onRename={rename}
    />
  );
  async function useReference(item) {
    const response = await fetch(item.url);
    if (!response.ok) throw new Error('Não foi possível carregar a referência');
    const blob = await response.blob();
    setDraft({
      id: 'reference-' + item.id,
      [item.kind === 'product' ? 'photo' : 'reference']: new File(
        [blob],
        item.title + '.' + item.extension,
        { type: blob.type }
      ),
    });
    setPage('create');
  }
  function open(id) {
    navigate(campaignUrl(id));
  }
  const historical = media.filter((m) => !m.product && m.run_id === 'assets');
  const selectedRun = runs.find((r) => r.id === selected);
  return (
    <div
      className={'app-shell' + (pinnedOpen ? ' menu-pinned' : '')}
      onPointerMove={(event) => {
        const button = event.target.closest(
          '.button:not(.warning):not(.action-danger):not(.text-red-700)'
        );
        if (!button || button.disabled) return;
        button.classList.add('spotlight-card', 'studio-spotlight');
        followSpotlight(button, event);
      }}
      onPointerOut={(event) => {
        const button = event.target.closest('.studio-spotlight');
        if (button && !button.contains(event.relatedTarget)) delete button.dataset.spotlight;
      }}
      onPointerCancel={(event) => {
        const button = event.target.closest('.studio-spotlight');
        if (button) delete button.dataset.spotlight;
      }}
    >
      <Tooltip text={menuOpen ? 'Fechar menu' : 'Abrir menu'}>
        <button
          ref={menuToggle}
          type="button"
          className={'menu-toggle' + (menuOpen ? ' is-open' : '')}
          aria-label={menuOpen ? 'Fechar menu' : 'Abrir menu'}
          aria-expanded={menuOpen}
          aria-controls="studio-navigation"
          onClick={() => setMenuOpen((open) => !open)}
        >
          {menuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </Tooltip>
      <button
        type="button"
        className={'menu-scrim' + (menuOpen && !pinnedOpen ? ' is-open' : '')}
        aria-label="Fechar menu"
        aria-hidden={!menuOpen || pinnedOpen}
        tabIndex={-1}
        onClick={() => setMenuOpen(false)}
      />
      <StudioSidebar
        page={page}
        session={session}
        open={menuOpen}
        groups={openGroups}
        onToggleGroup={toggleGroup}
        connected={connected}
        count={runs.length}
        onSignedOut={onSignedOut}
        onNavigate={(id, parent = false) => {
          if (id === 'create') setDraft(null);
          setPage(id);
          if (!pinnedOpen && !parent) setMenuOpen(false);
        }}
      />
      <div className="workspace">
        <header className="topbar">
          <StudioBreadcrumbs page={page} onNavigate={setPage} />
          <div className="flex items-center gap-3">
            <span className="badge">{busy ? 'Equipe trabalhando' : '4 agentes disponíveis'}</span>
            <div className="user-avatar">{initials}</div>
          </div>
        </header>
        <main ref={pageContent}>
          {page === 'result' && selected === retryNotice && retryNotice && (
            <Feedback
              tone="success"
              action={
                <button className="button small" onClick={() => setRetryNotice(null)}>
                  Dispensar
                </button>
              }
            >
              Solicitação de nova tentativa aceita. Acompanhe o andamento abaixo.
            </Feedback>
          )}
          {error && <p className="error mb-5">{error}</p>}
          {!connected && (
            <p className="hint mb-5">
              Conectando ao servidor local. As ações estarão disponíveis quando a conexão voltar.
            </p>
          )}
          {page === 'create' && (
            <div className="campaign-create-page">
              <div className="campaign-page-heading">
                <div>
                  <h1>Nova campanha</h1>
                  <p className="muted text-sm">Crie conteúdo com a identidade da {brandName}.</p>
                </div>
                {historical.length > 0 && (
                  <button type="button" className="button" onClick={() => setPage('gallery')}>
                    Ver biblioteca <ArrowUpRight size={15} aria-hidden="true" />
                  </button>
                )}
              </div>
              <CampaignForm
                key={draft?.id || 'new'}
                initial={draft}
                products={media.filter((m) => m.product)}
                busy={busy || !connected || !config}
                activityBusy={busy}
                configured={config?.configured}
                models={config?.models || []}
                imageModels={config?.image_models || []}
                onSubmit={create}
                onAssist={assist}
                onProductSaved={refresh}
              />
              <details className="campaign-team-guide">
                <summary>Como sua equipe trabalha</summary>
                <div className="campaign-team-grid">
                  {[
                    ['Director', 'Define a estratégia e coordena.'],
                    ['Social Media', 'Planeja conteúdo e calendário.'],
                    ['Copywriter', 'Escreve títulos e legendas.'],
                    ['Creative', 'Prepara a direção visual.'],
                  ].map(([title, desc]) => (
                    <div key={title}>
                      <strong>{title}</strong>
                      <p className="muted text-xs">{desc}</p>
                    </div>
                  ))}
                </div>
                <p className="muted text-xs">
                  Depois da revisão, as artes são produzidas quando solicitadas.
                </p>
              </details>
            </div>
          )}
          {page === 'references' && (
            <References
              key={route}
              token={session?.csrf || config?.token}
              connected={connected}
              onUse={useReference}
              onSaved={refresh}
            />
          )}
          {enabled('marketing') && (
            <div hidden={page !== 'consultations'}>
              <Consultations
                config={config}
                busy={busy || !connected}
                onConsult={consult}
                runs={runs}
              />
            </div>
          )}
          {page === 'erp' && <IntegrationModules only="erp" />}
          {page === 'ads' && <IntegrationModules only="meta_ads" />}
          {page === 'logs' && session?.role === 'OWNER' && <Logs />}
          {page === 'usage' && session?.role === 'OWNER' && <AgentUsage />}
          {['config', 'account', 'security', 'store', 'brandkit'].includes(page) && (
            <Settings
              page={page}
              session={session}
              onUpdated={onAccountUpdated}
              onNavigate={setPage}
            />
          )}
          {page === 'admin' && session?.role === 'OWNER' && (
            <AdminPanel onModulesChanged={onAccountUpdated} />
          )}
          {page === 'history' && (
            <>
              <div className="page-title">
                <div>
                  <p className="eyebrow">SEU HISTÓRICO CRIATIVO</p>
                  <h1>Campanhas</h1>
                </div>
                <button
                  className="button primary"
                  onClick={() => (setDraft(null), setPage('create'))}
                >
                  <Plus size={16} /> Nova campanha
                </button>
              </div>
              <div className="panel divide-y divide-slate-100">
                {runs.length ? (
                  runs.map((run) => (
                    <div className="run-row flex-wrap" key={run.id}>
                      <button
                        className="flex gap-4 items-center min-w-0 flex-1 text-left"
                        onClick={() => open(run.id)}
                      >
                        <div className="run-icon">
                          <FolderOpen size={22} />
                        </div>
                        <div className="min-w-0 flex-1 text-left">
                          <strong className="block truncate">
                            {run.title ||
                              run.outputs.brief?.request ||
                              run.outputs.campaign?.brief?.request ||
                              `Campanha ${brandName}`}
                          </strong>
                          <p className="muted text-xs mt-2">
                            {run.events[0]
                              ? new Date(run.events[0].time).toLocaleString('pt-BR')
                              : run.id}{' '}
                            ·{' '}
                            {run.events[0]?.mode === 'demo'
                              ? 'Demonstração'
                              : modelLabel(run.events[0]?.model) || 'Geração com IA'}
                          </p>
                        </div>
                        <span className="badge">
                          {
                            {
                              queued: 'Na fila',
                              running: 'Em andamento',
                              completed: 'Concluída',
                              failed: 'Interrompida',
                              interrupted: 'Parcial',
                            }[run.status]
                          }
                        </span>
                      </button>
                      {actions(run)}
                      <button
                        className="button small shrink-0"
                        aria-label="Abrir campanha"
                        onClick={() => open(run.id)}
                      >
                        <ChevronRight size={18} />
                      </button>
                    </div>
                  ))
                ) : (
                  <p className="p-10 muted">
                    Sua primeira campanha começa com uma ideia. Clique em Nova campanha.
                  </p>
                )}
              </div>
            </>
          )}
          {page === 'result' && (
            <>
              <div className="page-title">
                <div>
                  <p className="eyebrow">DO BRIEFING À ENTREGA</p>
                  <h1>Sua campanha</h1>
                </div>
                <button className="button" onClick={() => setPage('history')}>
                  Ver histórico
                </button>
              </div>
              {selectedRun ? (
                <>
                  <div className="mb-5">{actions(selectedRun)}</div>
                  <CampaignResults
                    key={selected}
                    run={selectedRun}
                    busy={busy || !connected}
                    onImage={image}
                    connected={connected}
                  />
                </>
              ) : (
                <p className="panel p-10">Carregando campanha…</p>
              )}
            </>
          )}
          {page === 'gallery' && (
            <Library
              media={media}
              brandName={brandName}
              token={session?.csrf || config?.token}
              busy={busy || !connected}
              onDeleted={(item) => {
                setMedia((current) => current.filter((entry) => entry.id !== item.id));
                refresh();
              }}
              onUseProduct={
                enabled('campaigns')
                  ? (item) => {
                      setDraft({ id: `product-${item.id}`, product_id: item.id });
                      setPage('create');
                    }
                  : null
              }
              onUploadProduct={
                enabled('references')
                  ? () => navigate(STUDIO_ROUTES.references + '?type=product')
                  : null
              }
            />
          )}
          <footer>
            {brandName} Studio <span>Campanhas em rascunho · revise antes de publicar</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
