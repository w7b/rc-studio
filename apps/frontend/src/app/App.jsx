import React, { useEffect, useState } from 'react';
import {
  Sparkles,
  LayoutDashboard,
  FolderOpen,
  Images,
  ArrowUpRight,
  Plus,
  ChevronRight,
  Wifi,
  PanelLeft,
  LoaderCircle,
  Network,
  Database,
  Megaphone,
  Gauge,
} from 'lucide-react';
import { api, post } from '../shared/api/client.js';
import References from '../features/references/References.jsx';
import CampaignActions from '../features/campaigns/CampaignActions.jsx';
import CampaignForm from '../features/campaigns/CampaignForm.jsx';
import CampaignResults from '../features/campaigns/CampaignResults.jsx';
import IntegrationModules from '../features/integrations/IntegrationModules.jsx';
import SystemCatalog from '../features/system/SystemCatalog.jsx';

export default function App() {
  const [sort, setSort] = useState('newest'),
    [search, setSearch] = useState('');
  const [page, setPage] = useState('create'),
    [config, setConfig] = useState(null),
    [runs, setRuns] = useState([]),
    [media, setMedia] = useState([]),
    [active, setActive] = useState(null),
    [selected, setSelected] = useState(null),
    [connected, setConnected] = useState(false),
    [error, setError] = useState(''),
    [draft, setDraft] = useState(null);
  async function refresh() {
    try {
      const [state, assets] = await Promise.all([api('/api/runs'), api('/api/media')]);
      setRuns(state.runs);
      setActive(state.active_id);
      setMedia(assets);
      setConnected(true);
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
      if (!stopped) timer = setTimeout(poll, 2000);
    }
    api('/api/config')
      .then(setConfig)
      .catch((e) => setError(e.message));
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, []);
  async function create(payload) {
    const result = await post('/api/runs', payload, config.token);
    setActive(result.id);
    setSelected(result.id);
    setPage('result');
    await refresh();
  }
  async function image(id, payload = {}) {
    await post('/api/runs/' + id + '/image', payload, config.token);
    setActive(id);
    await refresh();
  }
  async function retry(id) {
    const result = await post('/api/runs/' + id + '/retry', {}, config.token);
    setActive(result.id);
    setSelected(result.id);
    setPage('result');
    await refresh();
  }
  async function remove(id) {
    await post('/api/runs/' + id + '/delete', {}, config.token);
    if (selected === id) {
      setSelected(null);
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
      busy={!!active || !connected || !config}
      onRetry={retry}
      onDelete={remove}
      onEdit={edit}
    />
  );
  async function useReference(item) {
    const response = await fetch(item.url);
    if (!response.ok) throw new Error('Não foi possível carregar a referência');
    const blob = await response.blob();
    setDraft({
      id: 'reference-' + item.id,
      reference: new File([blob], item.title + '.' + item.extension, { type: blob.type }),
    });
    setPage('create');
  }
  function open(id) {
    setSelected(id);
    setPage('result');
  }
  const historical = media.filter((m) => !m.product && m.run_id === 'assets');
  const selectedRun = runs.find((r) => r.id === selected);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="wordmark"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            (setDraft(null), setPage('create'));
          }}
        >
          <span className="brand-symbol">
            rc<span>•</span>
          </span>
          <span>
            Real Center<strong>STUDIO</strong>
          </span>
        </a>
        <div className="workspace-label">WORKSPACE DE MARKETING</div>
        <nav>
          {[
            ['create', 'Criar campanha', Plus],
            ['history', 'Campanhas', FolderOpen],
            ['gallery', 'Biblioteca de artes', Images],
            ['references', 'Referências', Images],
            ['erp', 'ERP e relatórios', Database],
            ['ads', 'Meta Ads', Megaphone],
            ['usage', 'Consumo dos agentes', Gauge],
            ['system', 'Graphify e atividade', Network],
          ].map(([id, label, Icon]) => (
            <button
              key={id}
              onClick={() => {
                if (id === 'create') setDraft(null);
                setPage(id);
              }}
              className={page === id ? 'active' : ''}
            >
              <Icon size={18} />
              {label}
              {id === 'history' && <small>{runs.length}</small>}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <Sparkles size={20} />
          <strong>
            Sua equipe criativa,
            <br />
            no mesmo lugar.
          </strong>
          <p>
            Do primeiro briefing
            <br />à próxima campanha.
          </p>
        </div>
        <div className="sidebar-bottom">
          <span className={'connection-dot ' + (connected ? 'online' : '')} />
          {connected ? 'Ambiente local conectado' : 'Conectando ao ambiente…'}
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="text-sm text-slate-500">
            Marketing <ChevronRight size={13} className="inline mx-2" />
            <span className="text-slate-900">
              {page === 'create'
                ? 'Nova campanha'
                : page === 'history'
                  ? 'Campanhas'
                  : page === 'gallery'
                    ? 'Biblioteca'
                    : page === 'references'
                      ? 'Referências'
                      : {
                          erp: 'ERP e relatórios',
                          ads: 'Meta Ads',
                          usage: 'Consumo dos agentes',
                          system: 'Graphify e atividade',
                        }[page] || 'Resultados'}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="badge">{active ? 'Equipe trabalhando' : '4 agentes disponíveis'}</span>
            <div className="user-avatar">RC</div>
          </div>
        </header>
        <main>
          {error && <p className="error mb-5">{error}</p>}
          {!connected && (
            <p className="hint mb-5">
              Conectando ao servidor local. As ações estarão disponíveis quando a conexão voltar.
            </p>
          )}
          {page === 'create' && (
            <>
              <div className="hero">
                <div>
                  <p className="eyebrow">DA IDEIA À CAMPANHA</p>
                  <h1>
                    Vamos criar algo
                    <br />
                    <em>que chama atenção.</em>
                  </h1>
                  <p>
                    Seu briefing. Quatro especialistas.
                    <br />
                    Uma campanha com a cara da Real Center.
                  </p>
                </div>
                <div className="hero-art" aria-hidden="true">
                  <span className="orbit o1" />
                  <span className="orbit o2" />
                  <span className="hero-sticker">
                    <Sparkles size={36} />
                  </span>
                  <span className="floating-tag">100% foco em marketing ↗</span>
                </div>
              </div>
              <div className="grid xl:grid-cols-[minmax(0,1fr)_290px] gap-6 items-start">
                <CampaignForm
                  key={draft?.id || 'new'}
                  initial={draft}
                  products={media.filter((m) => m.product)}
                  busy={!!active || !connected || !config}
                  configured={config?.configured}
                  models={config?.models || []}
                  imageModels={config?.image_models || []}
                  onSubmit={create}
                  onAssist={(payload) => post('/api/brief-assist', payload, config.token)}
                />
                <aside className="space-y-5">
                  <section className="panel p-6">
                    <p className="eyebrow mb-5">COMO SUA EQUIPE TRABALHA</p>
                    {[
                      ['01', 'Director', 'Define a estratégia e coordena.'],
                      ['02', 'Social Media', 'Planeja conteúdo e calendário.'],
                      ['03', 'Copywriter', 'Escreve headlines e legendas.'],
                      ['04', 'Creative', 'Prepara a direção visual.'],
                    ].map(([n, title, desc]) => (
                      <div className="process" key={n}>
                        <span>{n}</span>
                        <div>
                          <strong>{title}</strong>
                          <p>{desc}</p>
                        </div>
                      </div>
                    ))}
                    <p className="muted text-xs mt-4">
                      Depois da revisão, o app produz a imagem quando solicitada.
                    </p>
                  </section>
                  {historical.length > 0 && (
                    <section className="panel overflow-hidden">
                      <img
                        className="inspiration"
                        src={historical.at(-1).url}
                        alt="Arte anterior da Real Center"
                      />
                      <div className="p-5">
                        <p className="eyebrow">FEITO POR AQUI</p>
                        <p className="text-sm font-semibold mt-2">
                          Referências que já fazem parte da nossa história.
                        </p>
                        <button
                          className="text-sm text-orange-700 mt-4 flex gap-2 items-center"
                          onClick={() => setPage('gallery')}
                        >
                          Explorar biblioteca <ArrowUpRight size={15} />
                        </button>
                      </div>
                    </section>
                  )}
                </aside>
              </div>
            </>
          )}
          {page === 'references' && (
            <References token={config?.token} connected={connected} onUse={useReference} />
          )}
          {['erp', 'ads'].includes(page) && <IntegrationModules type={page} />}
          {page === 'system' && <SystemCatalog />}
          {page === 'usage' && <SystemCatalog usageOnly />}
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
                            {run.outputs.brief?.request ||
                              run.outputs.campaign?.brief?.request ||
                              'Campanha Real Center'}
                          </strong>
                          <p className="muted text-xs mt-2">
                            {run.events[0]
                              ? new Date(run.events[0].time).toLocaleString('pt-BR')
                              : run.id}{' '}
                            ·{' '}
                            {run.events[0]?.mode === 'demo'
                              ? 'Demonstração'
                              : run.events[0]?.model?.split(':').pop() || 'Geração com IA'}
                          </p>
                        </div>
                        <span className="badge">
                          {
                            {
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
                    busy={!!active || !connected}
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
            <>
              <div className="page-title">
                <div>
                  <p className="eyebrow">ACERVO REAL CENTER</p>
                  <h1>Biblioteca de artes</h1>
                  <p className="muted mt-3">
                    Artes anteriores e novas imagens produzidas nas campanhas.
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap gap-4 mb-5">
                <label className="flex-1 min-w-48">
                  <span className="field-label">Buscar imagens</span>
                  <input
                    type="search"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Nome da imagem"
                  />
                </label>
                <label>
                  <span className="field-label">Ordenar por</span>
                  <select value={sort} onChange={(e) => setSort(e.target.value)}>
                    <option value="newest">Mais recentes</option>
                    <option value="oldest">Menos recentes</option>
                    <option value="az">A–Z</option>
                    <option value="za">Z–A</option>
                  </select>
                </label>
              </div>
              <div className="gallery">
                {media
                  .filter(
                    (m) =>
                      !m.product &&
                      m.name !== 'product.png' &&
                      m.name !== 'product.jpg' &&
                      !m.name.startsWith('reference.') &&
                      !m.name.startsWith('brand-reference')
                  )
                  .filter((m) =>
                    m.name.toLocaleLowerCase('pt-BR').includes(search.toLocaleLowerCase('pt-BR'))
                  )
                  .sort((a, b) =>
                    sort === 'az' || sort === 'za'
                      ? (sort === 'az' ? 1 : -1) *
                          a.name.localeCompare(b.name, 'pt-BR', { numeric: true }) ||
                        a.id.localeCompare(b.id)
                      : (sort === 'newest' ? -1 : 1) *
                          ((a.created_at || 0) - (b.created_at || 0)) || a.id.localeCompare(b.id)
                  )
                  .map((m) => (
                    <figure className="panel overflow-hidden" key={m.id}>
                      <a href={m.url} target="_blank" rel="noreferrer">
                        <img loading="lazy" src={m.url} alt={m.name} />
                      </a>
                      <figcaption className="p-4">
                        <p className="text-sm truncate font-semibold">{m.name}</p>
                        <a
                          className="text-xs text-orange-700 inline-block mt-3"
                          href={m.url}
                          download={m.name}
                        >
                          Baixar imagem ↗
                        </a>
                      </figcaption>
                    </figure>
                  ))}
              </div>
            </>
          )}
          <footer>
            Real Center Studio <span>Campanhas em rascunho · revise antes de publicar</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
