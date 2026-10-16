import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, RefreshCw } from '../../shared/icons.js';
import { systemService } from '../../services/system.js';

// Replaces the old Graphify catalog. That described the product's own source code, which
// no store could act on; this describes what actually happened.
const LABELS = {
  run_started: 'Campanha iniciada',
  run_completed: 'Campanha concluída',
  run_failed: 'Campanha falhou',
  run_queued: 'Na fila',
  assist_completed: 'Briefing melhorado',
  assist_failed: 'Assistência falhou',
  image_completed: 'Arte gerada',
  image_failed: 'Arte falhou',
  repair_started: 'Correção de schema',
  agent_config: 'Agente configurado',
  started: 'Agente iniciou',
  thinking: 'Agente processando',
  response_received: 'Resposta recebida',
  completed: 'Agente concluiu',
  failed: 'Agente falhou',
  image_started: 'Gerando arte',
  image_skipped: 'Arte já existente',
  delegated: 'Delegado',
  run_dequeued: 'Saiu da fila',
  assist_started: 'Melhorando briefing',
  upload_saved: 'Upload salvo',
};

const FAILURES = new Set(['run_failed', 'assist_failed', 'image_failed', 'failed']);

export default function Logs() {
  const [data, setData] = useState(null),
    [error, setError] = useState(''),
    [onlyFailures, setOnlyFailures] = useState(false),
    [store, setStore] = useState('');

  async function load() {
    try {
      setData(await systemService.getLogs());
      setError('');
    } catch (failure) {
      setError(failure.message);
    }
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 8000);
    return () => clearInterval(timer);
  }, []);

  const stores = useMemo(
    () => [...new Set((data?.entries || []).map((entry) => entry.tenant).filter(Boolean))].sort(),
    [data]
  );

  const entries = useMemo(() => {
    let rows = data?.entries || [];
    if (onlyFailures) rows = rows.filter((entry) => FAILURES.has(entry.event));
    if (store) rows = rows.filter((entry) => entry.tenant === store);
    return rows;
  }, [data, onlyFailures, store]);

  return (
    <>
      <div className="page-title">
        <div>
          <h1>Logs</h1>
          <p className="muted mt-3">
            {data?.scope === 'platform'
              ? 'Atividade recente de todas as lojas.'
              : 'Atividade recente desta instalação.'}
          </p>
        </div>
        <button className="button" type="button" onClick={load}>
          <RefreshCw size={14} /> Atualizar
        </button>
      </div>

      {error ? (
        <p className="auth-error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="panel p-6">
        <div className="logs-filters">
          <label className="field-label">
            Loja
            <select value={store} onChange={(event) => setStore(event.target.value)}>
              <option value="">Todas</option>
              {stores.map((slug) => (
                <option key={slug} value={slug}>
                  {slug}
                </option>
              ))}
            </select>
          </label>
          <label className="logs-toggle">
            <input
              type="checkbox"
              checked={onlyFailures}
              onChange={(event) => setOnlyFailures(event.target.checked)}
            />
            Só falhas
          </label>
          <span className="muted">{entries.length} registros</span>
        </div>

        {entries.length === 0 ? (
          <p className="muted">Nada registrado ainda.</p>
        ) : (
          <ul className="logs-list">
            {entries.map((entry, index) => (
              <li
                key={`${entry.run_id}-${entry.time}-${index}`}
                className={FAILURES.has(entry.event) ? 'log-row log-row-failed' : 'log-row'}
              >
                <time dateTime={entry.time}>
                  {entry.time ? new Date(entry.time).toLocaleString('pt-BR') : '—'}
                </time>
                <span className="log-event">
                  {FAILURES.has(entry.event) ? (
                    <AlertTriangle size={13} aria-hidden="true" />
                  ) : null}
                  {LABELS[entry.event] || entry.event}
                </span>
                <span className="log-meta">
                  {entry.tenant ? <strong>{entry.tenant}</strong> : null}
                  {entry.agent ? ` · ${entry.agent}` : ''}
                  {entry.error_type ? ` · ${entry.error_type}` : ''}
                </span>
                <code className="log-run">{entry.run_id}</code>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
