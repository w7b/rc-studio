import React, { useEffect, useState } from 'react';
import { Activity, Coins, FolderOpen, Image, RefreshCw, Store, Users, Zap } from 'lucide-react';
import { api } from '../../shared/api/client.js';
import MetricCard from '../../shared/components/MetricCard.jsx';
import Feedback from '../../shared/components/Feedback.jsx';
import { useRoute } from '../../shared/hooks/useRoute.js';

const number = (value) => Number(value || 0).toLocaleString('pt-BR');
const money = (value) =>
  Number(value || 0).toLocaleString('pt-BR', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 4,
  });
const PERIODS = { week: 'Esta semana', month: 'Este mês', all: 'Geral' };

export default function AdminMetrics() {
  const [route, navigate] = useRoute();
  const rawPeriod = new URLSearchParams(route.split('?')[1]).get('period');
  const period = Object.hasOwn(PERIODS, rawPeriod) ? rawPeriod : 'week';
  const [data, setData] = useState(null),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let current = true;
    setLoading(true);
    api('/api/admin/metrics')
      .then((result) => {
        if (current) {
          setData(result);
          setError('');
        }
      })
      .catch((failure) => {
        if (current) setError(failure.message);
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [revision]);

  const values = data?.periods[period];
  const days =
    data?.daily.filter((day) => !values?.start || day.date >= values.start.slice(0, 10)) || [];
  const maximum = Math.max(1, ...days.map((day) => day.requests));
  return (
    <section className="admin-metrics" aria-label="Métricas da plataforma" aria-busy={loading}>
      <div className="section-toolbar">
        <div>
          <p className="eyebrow">VISÃO DA PLATAFORMA</p>
          <h2>Clientes e consumo</h2>
        </div>
        <div className="period-filter" role="group" aria-label="Período das métricas">
          {Object.entries(PERIODS).map(([key, label]) => (
            <button
              key={key}
              className="button small"
              aria-pressed={key === period}
              onClick={() => navigate(`/admin?period=${key}`, { replace: true })}
            >
              {label}
            </button>
          ))}
          <button
            className="button small"
            disabled={loading}
            aria-label="Atualizar métricas"
            onClick={() => setRevision((n) => n + 1)}
          >
            <RefreshCw size={15} className={loading ? 'spin' : ''} />
          </button>
        </div>
      </div>
      {error && (
        <Feedback
          action={
            <button
              className="button small"
              disabled={loading}
              onClick={() => setRevision((n) => n + 1)}
            >
              {loading ? 'Carregando…' : 'Tentar novamente'}
            </button>
          }
        >
          {error}
        </Feedback>
      )}
      {!values ? (
        <p className="panel p-6" role="status">
          {loading ? 'Carregando métricas…' : 'Métricas indisponíveis.'}
        </p>
      ) : (
        <>
          <div className="metrics-grid">
            <MetricCard
              icon={Store}
              label="Novos clientes"
              value={number(values.new_stores)}
              detail={`${number(data.stores)} lojas cadastradas no total`}
            />
            <MetricCard
              icon={Users}
              label="Novos usuários"
              value={number(values.new_users)}
              detail="Cadastros de pessoas no período"
            />
            <MetricCard
              icon={Activity}
              label="Lojas com atividade"
              value={number(values.active_stores)}
              detail={`${number(data.suspended_stores)} lojas suspensas no total`}
            />
            <MetricCard
              icon={FolderOpen}
              label="Campanhas iniciadas"
              value={number(values.campaigns)}
              detail={`${number(values.completed)} concluídas · ${number(values.failed)} com falha no período`}
            />
            <MetricCard
              icon={Zap}
              label="Chamadas de IA"
              value={number(values.requests)}
              detail={`${number(values.brief_assists)} assistências de briefing iniciadas`}
            />
            <MetricCard
              icon={Zap}
              label="Tokens consumidos"
              value={number(values.input_tokens + values.output_tokens)}
              detail={`${number(values.input_tokens)} entrada · ${number(values.output_tokens)} saída · ${number(values.cached_input_tokens)} em cache`}
            />
            <MetricCard
              icon={Image}
              label="Imagens produzidas"
              value={number(values.images)}
              detail="Respostas de geração registradas"
            />
            <MetricCard
              icon={Coins}
              label="Custo estimado conhecido"
              value={money(values.known_cost_usd)}
              detail={
                values.unpriced_records
                  ? `${number(values.unpriced_records)} registros sem preço · total parcial`
                  : 'Estimativa em USD, sem conversão cambial'
              }
            />
          </div>
          <figure className="panel usage-chart">
            <figcaption>
              <strong>Chamadas de IA por dia</strong>
              <span>Até 30 dias · {data.timezone}</span>
            </figcaption>
            <div className="usage-bars" aria-hidden="true">
              {days.map((day) => (
                <div
                  className="usage-day"
                  key={day.date}
                  title={`${day.date}: ${number(day.requests)} chamadas`}
                >
                  <span
                    style={{ height: `${Math.max(2, (day.requests / maximum) * 100)}%` }}
                    className={day.requests ? 'has-usage' : ''}
                  />
                </div>
              ))}
            </div>
            <details>
              <summary>Ver valores diários</summary>
              <div className="table-scroll">
                <table className="system-table">
                  <caption className="sr-only">Consumo diário de IA</caption>
                  <thead>
                    <tr>
                      <th scope="col">Data</th>
                      <th scope="col">Chamadas</th>
                      <th scope="col">Tokens</th>
                      <th scope="col">Imagens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {days.map((day) => (
                      <tr key={day.date}>
                        <td>{day.date.split('-').reverse().join('/')}</td>
                        <td>{number(day.requests)}</td>
                        <td>{number(day.input_tokens + day.output_tokens)}</td>
                        <td>{number(day.images)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
            {days.every((day) => !day.requests) && (
              <p className="muted">Nenhum consumo de IA registrado neste período.</p>
            )}
          </figure>
          <details className="metric-notes">
            <summary>Como os números são calculados</summary>
            <ul>
              {data.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
            <p>
              {number(values.legacy_records)} registros antigos · {number(values.undated_records)}{' '}
              sem data.
            </p>
          </details>
          <p className="metric-updated">
            Atualizado em{' '}
            {new Date(data.generated_at).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' })}
          </p>
        </>
      )}
    </section>
  );
}
