import React, { useEffect, useState } from 'react';
import { api } from '../../shared/api/client.js';

export default function SystemCatalog({ usageOnly = false }) {
  const [data, setData] = useState(null),
    [events, setEvents] = useState([]),
    [error, setError] = useState('');
  const [query, setQuery] = useState(''),
    [selected, setSelected] = useState('');
  useEffect(() => {
    let stopped = false,
      timer;
    async function refresh() {
      try {
        const value = await api(usageOnly ? '/api/usage' : '/api/system');
        const activity = usageOnly ? [] : await api('/api/system/activity');
        if (!stopped) {
          setData(value);
          setEvents(activity);
          setError('');
        }
      } catch (e) {
        if (!stopped) setError(e.message);
      }
      if (!stopped) timer = setTimeout(refresh, 5000);
    }
    refresh();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [usageOnly]);
  const number = (n) => Number(n || 0).toLocaleString('pt-BR');
  if (usageOnly)
    return (
      <>
        <div className="page-title">
          <div>
            <p className="eyebrow">OBSERVABILIDADE</p>
            <h1>Consumo dos agentes</h1>
            <p className="muted mt-3">
              Campanhas e consultas ao Creative Producer, por agente e modelo.
            </p>
          </div>
        </div>
        {error && <p className="error">{error}</p>}
        {!data ? (
          <p>Carregando consumo…</p>
        ) : (
          <>
            <div className="grid sm:grid-cols-3 gap-5 mb-6">
              {[
                ['Entrada', data.input_tokens],
                ['Saída', data.output_tokens],
                ['Execuções registradas', data.record_count],
              ].map(([label, value]) => (
                <div key={label} className="panel p-6">
                  <p className="muted">{label}</p>
                  <h2 className="mt-2">{number(value)}</h2>
                </div>
              ))}
            </div>
            <div className="panel p-6 overflow-auto">
              <table className="system-table">
                <thead>
                  <tr>
                    <th>Agente / modelo</th>
                    <th>Chamadas</th>
                    <th>Entrada</th>
                    <th>Saída</th>
                    <th>Entrada em cache</th>
                    <th>Gravação de cache</th>
                  </tr>
                </thead>
                <tbody>
                  {data.agents.map((r) => (
                    <tr key={r.agent + r.model}>
                      <td>
                        {r.agent}
                        <small className="block muted">{r.model}</small>
                      </td>
                      <td>{number(r.requests)}</td>
                      <td>{number(r.input_tokens)}</td>
                      <td>{number(r.output_tokens)}</td>
                      <td>{number(r.cached_input_tokens)}</td>
                      <td>{number(r.cache_write_input_tokens)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!data.agents.length && <p className="muted">Ainda não há consumo registrado.</p>}
            </div>
            <section className="panel p-6 mt-6">
              <h2>Como interpretar</h2>
              <ul className="list-disc pl-5 mt-4 space-y-2">
                {data.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
              <p className="muted text-sm mt-4">
                Os totais vêm dos registros locais disponíveis, incluindo tentativas com falha. Não
                representam a fatura da conta. Imagens aparecem no custo de cada campanha e podem
                ter tokens não informados pelo provedor.
              </p>
            </section>
          </>
        )}
      </>
    );
  const graph = data?.graph || {},
    nodes = graph.nodes || [],
    edges = graph.links || graph.edges || [];
  const source = (e) => (typeof e.source === 'object' ? e.source.id : e.source);
  const target = (e) => (typeof e.target === 'object' ? e.target.id : e.target);
  const matches = nodes.filter((n) =>
    `${n.label || n.id} ${n.source_file || ''}`
      .toLocaleLowerCase('pt-BR')
      .includes(query.toLocaleLowerCase('pt-BR'))
  );
  const node = nodes.find((n) => n.id === selected);
  const related = edges.filter((e) => source(e) === selected || target(e) === selected);
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">MAPA DO SISTEMA</p>
          <h1>Graphify e atividade</h1>
          <p className="muted mt-3">
            Estrutura do código, alterações entre reinicializações e eventos das campanhas.
          </p>
        </div>
        <span className="badge">
          {{
            ready: 'Atualizado',
            building: 'Atualizando',
            pending: 'Aguardando',
            failed: 'Falha na atualização',
          }[data?.status] || 'Carregando'}
        </span>
      </div>
      {error && <p className="error">{error}</p>}
      {data?.message && (
        <p className="error">
          {data.message} ({data.error_type})
        </p>
      )}
      <p className="hint mb-5">
        Extração local de código: 0 tokens de IA. Documentos são catalogados por arquivo; relações
        semânticas não são inferidas. Atualização automática ao iniciar o servidor, quando houver
        alterações.
      </p>
      {data?.updated_at && (
        <p className="muted mb-5">
          {number(data.files)} arquivos · {number(data.nodes)} elementos · {number(data.edges)}{' '}
          relações · {new Date(data.updated_at).toLocaleString('pt-BR')}
        </p>
      )}
      {(data?.health?.dangling_endpoint_edges > 0 ||
        data?.health?.directed_same_endpoint_collapsed_edges > 0) && (
        <p className="hint mb-5">
          Mapa parcial: {number(data.health.dangling_endpoint_edges)} relações apontam para
          elementos não resolvidos e {number(data.health.directed_same_endpoint_collapsed_edges)}{' '}
          relações entre os mesmos elementos foram agrupadas pelo Graphify. Confirme no código antes
          de tirar conclusões.
        </p>
      )}
      <div className="grid lg:grid-cols-2 gap-5">
        <section className="panel p-6">
          <h2 className="mb-4">Explorar elementos</h2>
          <input
            aria-label="Buscar no mapa"
            placeholder="Buscar função, classe ou arquivo"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <p className="muted text-xs my-3">{matches.length} resultados · exibindo até 100</p>
          <div className="max-h-96 overflow-auto">
            {matches.slice(0, 100).map((n) => (
              <button
                className={'catalog-node ' + (n.id === selected ? 'selected' : '')}
                key={n.id}
                onClick={() => setSelected(n.id)}
              >
                <strong>{n.label || n.id}</strong>
                <small>
                  {n.source_file} {n.source_location}
                </small>
              </button>
            ))}
          </div>
        </section>
        <section className="panel p-6">
          <h2>{node?.label || 'Selecione um elemento'}</h2>
          {node && (
            <>
              <p className="muted text-sm my-3">
                {node.source_file} {node.source_location} · {node.community_name}
              </p>
              <h3 className="font-semibold">Relações extraídas · {related.length}</h3>
              <div className="max-h-96 overflow-auto mt-3">
                {related.slice(0, 100).map((e, i) => {
                  const id = source(e) === selected ? target(e) : source(e);
                  const other = nodes.find((n) => n.id === id);
                  return (
                    <button className="catalog-node" key={i} onClick={() => setSelected(id)}>
                      <span>
                        {source(e) === selected ? '→' : '←'} {other?.label || id}
                      </span>
                      <small>
                        {e.relation || e.label || e.type || 'relação extraída'} ·{' '}
                        {e.confidence || 'EXTRACTED'}
                      </small>
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </section>
      </div>
      <details className="panel p-6 mt-5">
        <summary className="cursor-pointer font-semibold">
          Arquivos catalogados e coesão dos grupos
        </summary>
        <div className="max-h-64 overflow-auto mt-4">
          {(data?.files_catalog || []).map((file) => (
            <p key={file} className="text-sm">
              {file}
            </p>
          ))}
        </div>
        <pre className="text-xs mt-4">{JSON.stringify(data?.cohesion || {}, null, 2)}</pre>
      </details>
      <details className="panel p-6 mt-5">
        <summary className="cursor-pointer font-semibold">Alterações detectadas ao iniciar</summary>
        {[...(data?.history || [])].reverse().map((change) => (
          <div className="mt-4" key={change.time}>
            <strong>{new Date(change.time).toLocaleString('pt-BR')}</strong>
            {[
              ['added', 'Adicionados'],
              ['modified', 'Modificados'],
              ['removed', 'Removidos'],
            ].map(([key, label]) => (
              <p className="text-sm break-all mt-2" key={key}>
                {label}: {change[key].join(', ') || 'Nenhum'}
              </p>
            ))}
          </div>
        ))}
      </details>
      <section className="panel p-6 mt-5">
        <h2>Atividade recente</h2>
        <p className="muted text-sm my-3">
          Até 250 eventos de campanhas e consultas. Use os diagnósticos da campanha para investigar
          uma falha.
        </p>
        <div className="max-h-96 overflow-auto">
          {events.map((e, i) => (
            <div className="event" key={i}>
              <time>{new Date(e.time).toLocaleString('pt-BR')}</time>
              <strong>{e.agent || 'Sistema'}</strong>
              <span>
                {e.event}
                {e.error_type ? ' · ' + e.error_type : ''}
              </span>
            </div>
          ))}
          {!events.length && <p className="muted">Nenhum evento registrado.</p>}
        </div>
      </section>
    </>
  );
}
