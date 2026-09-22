import React, { useRef, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import Form from '../../shared/components/Form.jsx';
import Textarea from '../../shared/components/Textarea.jsx';
import Feedback from '../../shared/components/Feedback.jsx';
import SearchSelect from '../../shared/components/SearchSelect.jsx';
import { modelLabel } from '../../shared/catalog/models.js';

const labels = {
  objective: 'Objetivo',
  audiences: 'Públicos',
  name: 'Nome',
  hypothesis: 'Hipótese',
  targeting: 'Segmentação',
  exclusions: 'Exclusões',
  channels: 'Canais',
  tests: 'Testes',
  variants: 'Variantes',
  success_criterion: 'Critério de avaliação',
  suggested_budget: 'Orçamento sugerido',
  amount_brl: 'Valor em BRL',
  period: 'Período',
  rationale: 'Justificativa',
  approval_required: 'Exige aprovação humana',
  measurement_plan: 'Plano de medição',
  missing_data: 'Dados pendentes',
  summary: 'Resumo',
  findings: 'Análise de resultados',
  competitors: 'Concorrentes',
  competitor: 'Concorrente',
  source_id: 'Fonte',
  evidence: 'Trecho fornecido',
  analysis: 'Análise',
  seo_recommendations: 'Recomendações de SEO',
  action: 'Ação',
  priority: 'Prioridade',
  verification: 'Como verificar',
};

function Delivery({ value }) {
  if (value === null) return <span>Não informado</span>;
  if (typeof value === 'boolean') return <span>{value ? 'Sim' : 'Não'}</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <p className="muted">Nenhum item informado.</p>;
    return (
      <ul className="space-y-3 pl-4 list-disc">
        {value.map((item, index) => (
          <li key={index}>
            <Delivery value={item} />
          </li>
        ))}
      </ul>
    );
  }
  if (typeof value === 'object')
    return (
      <dl className="space-y-3">
        {Object.entries(value).map(([key, item]) => (
          <div key={key}>
            <dt className="font-semibold">{labels[key] || key}</dt>
            <dd className="mt-1 whitespace-pre-wrap break-words">
              <Delivery value={item} />
            </dd>
          </div>
        ))}
      </dl>
    );
  return <span>{String(value)}</span>;
}

export default function Consultations({ config, busy, onConsult, runs = [] }) {
  const [role, setRole] = useState('performance');
  const [request, setRequest] = useState('');
  const [facts, setFacts] = useState('');
  const [sources, setSources] = useState([]);
  const [model, setModel] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const submitting = useRef(false);
  const models = config?.models || [];
  const selectedModel = model || models.find((item) => item.available)?.id || '';
  const available = models.some((item) => item.id === selectedModel && item.available);

  // Only finished campaigns carry deliveries worth advising on.
  const finished = runs.filter((run) => run.status === 'completed');

  function campaignTitle(run) {
    return (
      run.title || run.outputs?.brief?.request || run.outputs?.campaign?.brief?.request || run.id
    );
  }

  function campaignEvidence(run) {
    const campaign = run.outputs?.campaign;
    const copy = campaign?.copywriting || run.outputs?.copywriter;
    const social = campaign?.social || run.outputs?.social_media;
    const lines = [
      `Campanha: ${campaignTitle(run)}`,
      `Briefing: ${campaign?.brief?.request || run.outputs?.brief?.request || 'não registrado'}`,
      copy?.headline ? `Headline: ${copy.headline}` : null,
      copy?.feed_caption ? `Legenda do feed: ${copy.feed_caption}` : null,
      social?.strategy ? `Estratégia de social: ${social.strategy}` : null,
      campaign?.director?.concept ? `Conceito: ${campaign.director.concept}` : null,
    ].filter(Boolean);
    return lines.join('\n');
  }

  function addCampaign(runId) {
    const run = finished.find((item) => item.id === runId);
    if (!run) return;
    setSources((current) =>
      current.some((item) => item.runId === runId)
        ? current
        : [
            ...current,
            {
              runId,
              title: `Campanha · ${campaignTitle(run)}`.slice(0, 200),
              url: '',
              content: campaignEvidence(run).slice(0, 20000),
            },
          ]
    );
  }

  function sourceChange(index, key, value) {
    setSources((current) =>
      current.map((item, i) => (i === index ? { ...item, [key]: value } : item))
    );
  }

  async function submit(event) {
    event.preventDefault();
    if (submitting.current || busy || !available || !request.trim()) return;
    submitting.current = true;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      setResult(
        await onConsult({
          role,
          request: request.trim(),
          model_id: selectedModel,
          confirmed_facts: facts
            .split('\n')
            .map((line) => line.trim())
            .filter(Boolean),
          sources: sources.map(({ runId: _ignored, ...item }, index) => ({
            ...item,
            id: `fonte-${index + 1}`,
            url: item.url.trim() || null,
          })),
        })
      );
    } catch (failure) {
      setError(failure.message);
    } finally {
      submitting.current = false;
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="eyebrow">ESPECIALISTAS SOB DEMANDA</p>
        <h1>Consultoria de marketing</h1>
        <p className="muted mt-2">
          Planeje mídia paga ou analise resultados e SEO com os dados da sua loja.
        </p>
      </header>
      <Form className="panel p-6 space-y-5" onSubmit={submit}>
        <label className="block">
          Especialista
          <select
            value={role}
            disabled={loading}
            onChange={(event) => {
              setRole(event.target.value);
              setResult(null);
            }}
          >
            <option value="performance">Performance Marketing Manager</option>
            <option value="marketing_analyst">Marketing Analyst + SEO</option>
          </select>
        </label>
        <label className="block">
          O que você precisa?
          <Textarea
            required
            maxLength={12000}
            rows={4}
            value={request}
            disabled={loading}
            onChange={(event) => setRequest(event.target.value)}
          />
        </label>
        <label className="block">
          Fatos confirmados, um por linha
          <Textarea
            rows={3}
            value={facts}
            disabled={loading}
            onChange={(event) => setFacts(event.target.value)}
          />
        </label>
        <section className="space-y-4" aria-label="Fontes fornecidas">
          <div>
            <h2>Dados e fontes</h2>
            <p className="muted text-sm">
              Cole os trechos dos relatórios ou páginas que sustentam sua análise. Links não são
              acessados automaticamente. Sem dados, o Analyst indica as lacunas.
            </p>
          </div>
          {sources.map((source, index) => (
            <fieldset key={index} className="space-y-3" disabled={loading}>
              <legend>Fonte {index + 1}</legend>
              <label className="block">
                Título
                <input
                  required
                  value={source.title}
                  onChange={(event) => sourceChange(index, 'title', event.target.value)}
                />
              </label>
              <label className="block">
                URL da fonte (opcional)
                <input
                  type="url"
                  pattern="https?://.*"
                  value={source.url}
                  onChange={(event) => sourceChange(index, 'url', event.target.value)}
                />
              </label>
              <label className="block">
                Conteúdo verificável
                <Textarea
                  required
                  rows={3}
                  value={source.content}
                  onChange={(event) => sourceChange(index, 'content', event.target.value)}
                />
              </label>
              <button
                type="button"
                className="button small"
                onClick={() => setSources((current) => current.filter((_, i) => i !== index))}
              >
                Remover fonte {index + 1}
              </button>
            </fieldset>
          ))}
          <div className="consultation-campaign-picker">
            <SearchSelect
              label="Basear em uma campanha já criada"
              value=""
              disabled={loading || !finished.length || sources.length >= 30}
              placeholder={
                finished.length ? 'Buscar campanha concluída…' : 'Nenhuma campanha concluída ainda'
              }
              options={finished.map((run) => ({
                value: run.id,
                label: campaignTitle(run),
                description: run.events?.[0]?.time
                  ? new Date(run.events[0].time).toLocaleDateString('pt-BR')
                  : run.id,
              }))}
              onChange={addCampaign}
            />
            <p className="muted text-xs">
              A campanha entra como fonte, com briefing, headline e conceito. É assim que o
              consultor trabalha sobre dado real em vez de suposição.
            </p>
          </div>
          <button
            type="button"
            className="button small"
            disabled={loading || sources.length >= 30}
            onClick={() =>
              setSources((current) => [...current, { title: '', url: '', content: '' }])
            }
          >
            Adicionar fonte
          </button>
        </section>
        <label className="block">
          Modelo
          <select
            value={selectedModel}
            disabled={loading}
            onChange={(event) => setModel(event.target.value)}
          >
            <option value="" disabled>
              Selecione um modelo disponível
            </option>
            {models.map((item) => (
              <option key={item.id} value={item.id} disabled={!item.available}>
                {modelLabel(item.id)}
                {!item.available ? ' — indisponível' : ''}
              </option>
            ))}
          </select>
        </label>
        <p className="muted text-sm">
          Cada execução consome uma consulta da cota e tokens de IA. O orçamento de mídia é apenas
          uma sugestão para sua aprovação. Não há publicação ou gasto em anúncios.
        </p>
        {!available && (
          <Feedback tone="info">Configure um modelo de texto para executar a consulta.</Feedback>
        )}
        {error && <Feedback>{error}</Feedback>}
        <button
          className="button primary"
          disabled={loading || busy || !available || !request.trim()}
          aria-busy={loading}
        >
          {loading && <LoaderCircle size={16} className="animate-spin" />}Executar consulta
        </button>
        {loading && (
          <p role="status" className="muted">
            O especialista está preparando a resposta. Aguarde a conclusão.
          </p>
        )}
      </Form>
      {result && (
        <section className="panel p-6 space-y-5" aria-label="Resultado da consulta">
          <h2>
            {result.role === 'performance'
              ? 'Plano de mídia paga'
              : 'Análise e recomendações de SEO'}
          </h2>
          <Delivery value={result.result} />
          {result.sources.length > 0 && (
            <div>
              <h3>Fontes fornecidas</h3>
              <ul className="list-disc pl-4">
                {result.sources.map((source) => (
                  <li key={source.id}>
                    {source.id}:{' '}
                    {source.url ? (
                      <a href={source.url} target="_blank" rel="noreferrer">
                        {source.title}
                      </a>
                    ) : (
                      source.title
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="muted text-sm">
            Custo estimado da consulta:{' '}
            {result.usage?.total_cost_usd == null
              ? 'indisponível'
              : `US$ ${result.usage.total_cost_usd.toFixed(6)}`}{' '}
            · {(result.usage?.text?.total_tokens || 0).toLocaleString('pt-BR')} tokens
          </p>
        </section>
      )}
    </div>
  );
}
