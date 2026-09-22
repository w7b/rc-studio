import React, { useState } from 'react';
import { Copy, Download, ImagePlus, Image, CheckCircle, LoaderCircle } from 'lucide-react';
import ImageRevision from '../image_revision/ImageRevision.jsx';
import AgentTeam from '../agent_team/AgentTeam.jsx';
import Diagnostics from './Diagnostics.jsx';
import FieldHelp from '../../shared/components/FieldHelp.jsx';
import CostSummary from './CostSummary.jsx';
// Short, concrete explanations. A hint that restates the label teaches nothing, so each
// one says what the field is for or what makes it right.
const hints = {
  strategy: 'O raciocínio por trás da campanha: a quem ela fala e o que quer que aconteça.',
  concept: 'A ideia central que amarra texto e arte. Uma frase, não um slogan pronto.',
  headline: 'A chamada principal da arte. Curta, lida de relance, sem depender da legenda.',
  cta: 'A ação que você quer do cliente: visitar a loja, chamar no WhatsApp, aproveitar a oferta.',
  feed_caption: 'A legenda publicada junto da imagem no Feed, com gancho, informação e CTA.',
  leaflet_copy: 'O texto do encarte impresso ou digital, quando a loja usa esse formato.',
  whatsapp_draft: 'Mensagem pronta para enviar em lista ou status do WhatsApp.',
  stories: 'A sequência de quadros do Stories, na ordem em que serão publicados.',
  audience_hypothesis:
    'Para quem a campanha foi pensada. É hipótese a validar, não dado confirmado.',
  visual_direction: 'Como a arte deve parecer: clima, cores, enquadramento e referências.',
  leaflet_brief: 'Instruções de produção do encarte, separadas do texto que ele carrega.',
  assets: 'Cada peça que a campanha prevê, com formato e dimensões.',
  layout: 'Onde cada elemento fica na arte e quanto espaço ocupa.',
  hierarchy: 'A ordem de leitura: o que o olho encontra primeiro, depois e por último.',
  brand_pending: 'O que falta no Brand Kit para a arte ficar fiel à identidade da loja.',
  assumptions: 'O que foi suposto por falta de informação confirmada. Revise antes de publicar.',
  pending_information: 'Dados que ninguém confirmou e que a IA não inventou de propósito.',
  review_notes: 'Contradições e ressalvas que o Director encontrou ao revisar as entregas.',
  carousel_cards: 'Os cards do carrossel, numerados na ordem de publicação.',
  calendar: 'Quando publicar cada peça.',
};

const titles = {
  strategy: 'Estratégia',
  concept: 'Conceito',
  headline: 'Headline',
  cta: 'CTA',
  feed_caption: 'Legenda do Feed',
  leaflet_copy: 'Texto do encarte',
  whatsapp_draft: 'WhatsApp',
  stories: 'Stories',
  number: 'Quadro',
  text: 'Texto',
  visual: 'Visual',
  objective: 'Objetivo',
  calendar: 'Calendário',
  timing: 'Quando',
  format: 'Formato',
  feed_suggestion: 'Sugestão de Feed',
  reel_suggestion: 'Sugestão de Reel',
  audience_hypothesis: 'Público proposto',
  visual_direction: 'Direção visual',
  leaflet_brief: 'Briefing do encarte',
  assets: 'Peças',
  dimensions: 'Dimensões',
  layout: 'Composição',
  hierarchy: 'Hierarquia',
  brand_pending: 'Pendências da marca',
  assumptions: 'Suposições',
  pending_information: 'Informações pendentes',
  review_notes: 'Revisão do Director',
  carousel_cards: 'Cards do carrossel',
  body: 'Texto do card',
};
function Fields({ value }) {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'object')
    return <p className="whitespace-pre-wrap leading-relaxed text-sm">{String(value)}</p>;
  if (Array.isArray(value))
    return (
      <div className="space-y-3">
        {value.length ? (
          value.map((v, i) => (
            <div className="nested" key={i}>
              <Fields value={v} />
            </div>
          ))
        ) : (
          <p className="muted text-sm">Sem itens.</p>
        )}
      </div>
    );
  return (
    <div className="space-y-5">
      {Object.entries(value)
        .filter(
          ([, item]) =>
            item !== null &&
            item !== undefined &&
            item !== '' &&
            (!Array.isArray(item) || item.length > 0)
        )
        .map(([k, v]) => (
          <div key={k}>
            <h3 className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-2 field-title">
              {titles[k] || k}
              <FieldHelp text={hints[k]} />
            </h3>
            <Fields value={v} />
          </div>
        ))}
    </div>
  );
}
const labels = {
  repair_started: 'Tentativa de correção do agente (1/1)',
  repair_completed: 'Entrega corrigida',
  repair_exhausted: 'Limite de correção atingido',
  response_received: 'Resposta recebida; consumo registrado',
  validation_failed: 'Falha de validação',
  run_started: 'Campanha iniciada',
  started: 'Iniciou o trabalho',
  thinking: 'Processando',
  completed: 'Entrega concluída',
  run_completed: 'Campanha concluída',
  failed: 'Etapa interrompida',
  run_failed: 'Execução interrompida',
  image_started: 'Gerando arte',
  image_completed: 'Arte pronta',
  image_failed: 'Falha na geração de imagem',
};
const deliveryHelp = {
  copywriter: 'Textos preparados para legenda, chamada e outros canais da campanha.',
  social_media: 'Planejamento de público, formatos e calendário que orienta os textos.',
  creative: 'Orientações de composição, hierarquia e identidade usadas para produzir a arte.',
  marketing_director:
    'Revisão da estratégia, suposições e informações que ainda precisam ser confirmadas.',
};
export default function CampaignResults({ run, busy, onImage, connected }) {
  const [tab, setTab] = useState('copywriter'),
    [copied, setCopied] = useState(false),
    [error, setError] = useState(''),
    [starting, setStarting] = useState(false),
    [revision, setRevision] = useState(false);
  if (!run)
    return <div className="panel p-10 text-center muted">Selecione uma campanha no histórico.</div>;
  const outputs = run.outputs,
    caption = outputs.copywriter?.feed_caption;
  const demo = run.events[0]?.mode === 'demo';
  const lastFailure = [...run.events].reverse().find((e) => e.message);
  const file = (name) => `/api/runs/${run.id}/files/${name}`;
  async function copy() {
    try {
      await navigator.clipboard.writeText(caption);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      setError('Selecione a legenda e use Ctrl+C.');
    }
  }
  async function image() {
    setStarting(true);
    setError('');
    try {
      await onImage(run.id);
    } catch (e) {
      setError(e.message);
    } finally {
      setStarting(false);
    }
  }
  return (
    <div className="space-y-6">
      {revision && (
        <ImageRevision
          images={run.images}
          busy={busy}
          onClose={() => setRevision(false)}
          onSubmit={(payload) => onImage(run.id, payload)}
        />
      )}
      <div className="flex flex-wrap justify-between gap-3 items-center">
        <div>
          <p className="eyebrow">
            {demo ? 'DEMONSTRAÇÃO · RESPOSTAS FIXAS' : 'CAMPANHA · RASCUNHO'}
          </p>
          <h2 className="mt-1">
            {outputs.campaign?.director?.concept?.slice(0, 120) ||
              outputs.brief?.request?.slice(0, 100) ||
              'Campanha'}
          </h2>
        </div>
        {outputs.campaign && (
          <a className="button" href={file('campaign.json')} download>
            <Download size={16} /> Pacote JSON
          </a>
        )}
      </div>
      <AgentTeam run={run} connected={connected} />
      <CostSummary usage={run.usage} runId={run.id} />
      <Diagnostics run={run} />
      {run.status === 'interrupted' && (
        <p className="hint">
          Esta execução não está ativa neste servidor. As entregas parciais estão preservadas.
        </p>
      )}
      {run.status === 'failed' && (
        <p role="alert" className="error">
          {lastFailure?.message || 'Execução interrompida pela API. Confira os eventos abaixo.'}
        </p>
      )}
      <div className="grid xl:grid-cols-[1fr_1.1fr] gap-6">
        <section className="panel p-6">
          <div className="flex justify-between gap-2 items-center mb-5">
            <h2>Artes da campanha</h2>
            {outputs.campaign && !demo && (
              <button
                className="button small"
                disabled={busy || starting}
                onClick={() => (run.images.length ? setRevision(true) : image())}
              >
                <ImagePlus size={16} />
                {starting ? 'Iniciando…' : run.images.length ? 'Nova versão' : 'Gerar arte'}
              </button>
            )}
          </div>
          {run.images.length ? (
            <div className="grid gap-5">
              {run.images.map((img) => (
                <figure key={img.id}>
                  <a href={img.url} target="_blank" rel="noreferrer">
                    <img
                      className="result-image"
                      src={img.url}
                      alt={
                        img.name.startsWith('carousel-')
                          ? `Card ${Number(img.name.split('-')[1])} do carrossel`
                          : 'Arte gerada para esta campanha'
                      }
                    />
                  </a>
                  <a className="button small mt-3" href={img.url} download={img.name}>
                    <Download size={14} /> Baixar imagem
                  </a>
                </figure>
              ))}
            </div>
          ) : (
            <div className="image-empty">
              <Image size={38} />
              <strong>
                {run.events.at(-1)?.event === 'image_started'
                  ? 'Produzindo sua arte…'
                  : 'Sua arte vai aparecer aqui'}
              </strong>
              <p>
                {demo
                  ? 'O modo demonstração não produz imagens.'
                  : 'A produção usa o briefing, a copy e as referências enviadas.'}
              </p>
            </div>
          )}
          {error && <p className="error mt-3">{error}</p>}
        </section>
        <section className="panel p-6">
          <div className="flex justify-between items-center mb-5">
            <h2>Legenda pronta para usar</h2>
            <button className="button small" onClick={copy} disabled={!caption}>
              <Copy size={15} />
              {copied ? 'Copiada' : 'Copiar'}
            </button>
          </div>
          <div className="caption">
            {caption || 'O Copywriter prepara a legenda depois do plano do Social Media.'}
          </div>
          {caption && (
            <a
              className="text-sm text-orange-700 inline-flex gap-2 items-center mt-5"
              href={file('legenda-feed.txt')}
              download
            >
              <Download size={14} /> Baixar legenda .txt
            </a>
          )}
          <div className="divider my-6" />
          <h3 className="font-semibold text-sm mb-2">Headline e chamada</h3>
          <p className="font-semibold text-xl">
            {outputs.copywriter?.headline || 'Aguardando o Copywriter'}
          </p>
          <p className="muted text-sm mt-3">{outputs.copywriter?.cta}</p>
        </section>
      </div>
      <details className="panel p-6 campaign-deliveries">
        <summary>Detalhes da campanha</summary>
        <p className="muted mt-4 mb-5">
          Consulte os textos completos, o planejamento e as orientações usadas pelos agentes.
        </p>
        <div className="tabs" role="group" aria-label="Entregas da campanha">
          {[
            ['copywriter', 'Textos'],
            ['social_media', 'Planejamento'],
            ['creative', 'Direção da arte'],
            ['marketing_director', 'Revisão'],
          ].map(([id, label]) => (
            <button
              key={id}
              aria-pressed={tab === id}
              className={tab === id ? 'selected' : ''}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="muted mb-5">{deliveryHelp[tab]}</p>
        {outputs[tab] ? (
          <>
            <Fields value={outputs[tab]} />
            <a href={file(tab + '.json')} className="button small mt-6" download>
              <Download size={14} /> Baixar entrega
            </a>
          </>
        ) : (
          <p className="muted py-6">Essa entrega ainda não foi concluída.</p>
        )}
      </details>
      {!!run.inputs?.length && (
        <section className="panel p-6">
          <h2 className="mb-4">Referências utilizadas</h2>
          <div className="flex flex-wrap gap-4">
            {run.inputs.map((input) => (
              <figure key={input.id}>
                <img
                  src={input.url}
                  alt={input.name.startsWith('product') ? 'Foto do produto' : 'Referência visual'}
                  className="h-32 w-32 object-contain bg-slate-50 rounded-lg"
                />
                <figcaption className="text-xs text-slate-500 mt-2">
                  {input.name.startsWith('product')
                    ? 'Produto'
                    : input.name.startsWith('brand-reference')
                      ? 'Padrão da marca'
                      : 'Estilo visual enviado'}
                </figcaption>
              </figure>
            ))}
          </div>
        </section>
      )}
      <details className="panel p-6">
        <summary className="font-semibold cursor-pointer">
          Atividade dos agentes · {run.events.length} eventos
        </summary>
        <div className="mt-4 max-h-80 overflow-auto">
          {run.events.map((e, i) => (
            <div key={i} className="event">
              <time>{new Date(e.time).toLocaleTimeString('pt-BR')}</time>
              <strong>{e.agent || 'Equipe'}</strong>
              <span>
                {labels[e.event] || e.event}
                {e.error_type ? ' · ' + e.error_type : ''}
              </span>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}
