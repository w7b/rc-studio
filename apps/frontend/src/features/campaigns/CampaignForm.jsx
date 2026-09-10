import React, { useState, useEffect } from 'react';
import { ArrowRight, Sparkles, ImagePlus, FlaskConical } from 'lucide-react';
import BriefAssistant from '../briefing/BriefAssistant.jsx';
import UploadField from '../../shared/components/UploadField.jsx';
import { fileData, api } from '../../shared/api/client.js';

export default function CampaignForm({ products, busy, configured, onSubmit, onAssist, initial }) {
  const [formats, setFormats] = useState([]);
  const [publication, setPublication] = useState(
    initial?.publication || { kind: 'feed', preset: 'feed_portrait', slides: 1 }
  );
  useEffect(() => {
    api('/api/formats')
      .then(setFormats)
      .catch((e) => setError(e.message));
  }, []);
  function changeKind(kind) {
    setPublication({
      kind,
      preset: kind === 'story' || kind === 'reel_cover' ? kind : 'feed_portrait',
      slides: kind === 'carousel' ? 3 : 1,
    });
  }
  const [request, setRequest] = useState(initial?.request || ''),
    [facts, setFacts] = useState(
      initial?.confirmed_facts?.join('\n') || 'Produto: \nPreço: R$\nTítulo em destaque: '
    ),
    [mode, setMode] = useState(initial?.mode || 'live');
  const [image, setImage] = useState(initial?.generate_image ?? true),
    [product, setProduct] = useState(''),
    [photo, setPhoto] = useState(initial?.photo || null),
    [reference, setReference] = useState(initial?.reference || null),
    [helping, setHelping] = useState(false),
    [sending, setSending] = useState(false),
    [error, setError] = useState('');
  async function submit(e) {
    e.preventDefault();
    if (helping) return;
    setError('');
    setSending(true);
    try {
      await onSubmit({
        request,
        confirmed_facts: facts
          .split('\n')
          .map((x) => x.trim())
          .filter(Boolean),
        mode,
        publication,
        generate_image: mode === 'live' && image,
        product_id: photo ? null : product || null,
        upload: photo ? await fileData(photo) : null,
        reference_upload: reference ? await fileData(reference) : null,
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  }
  return (
    <form onSubmit={submit} className="panel p-6 md:p-8 space-y-6">
      {initial?.id?.startsWith('run-') && (
        <p className="hint">
          Editando o briefing e as referências. Ao gerar, uma nova versão será criada; a campanha
          original será preservada.
        </p>
      )}
      <div className="flex gap-3 items-start">
        <div className="step">01</div>
        <div>
          <h2>Conte sua ideia</h2>
          <p className="muted text-sm mt-1">
            O Director transforma seu pedido em uma campanha completa.
          </p>
        </div>
      </div>
      <label className="block">
        <span className="field-label">O que vamos criar?</span>
        <textarea
          required
          maxLength={12000}
          rows={4}
          value={request}
          onChange={(e) => setRequest(e.target.value)}
          placeholder="Crie uma campanha para o final de semana da Real Center. Destaque o suco de laranja com uma arte vibrante…"
        />
      </label>
      <BriefAssistant
        request={request}
        facts={facts}
        busy={busy || sending}
        configured={configured}
        onAssist={onAssist}
        onApply={setRequest}
        onBusy={setHelping}
      />
      <label className="block">
        <span className="field-label">
          Informações confirmadas <small>uma por linha</small>
        </span>
        <textarea rows={3} value={facts} onChange={(e) => setFacts(e.target.value)} />
      </label>
      <div className="divider" />
      <div className="flex gap-3 items-start">
        <div className="step">02</div>
        <div>
          <h2>Referências para o criativo</h2>
          <p className="muted text-sm mt-1">
            O app usa todas as imagens da pasta de referências da marca. Você também pode enviar uma
            referência adicional para esta campanha.
          </p>
        </div>
      </div>
      <div className="grid sm:grid-cols-2 gap-4">
        <label>
          <span className="field-label">Tipo de publicação</span>
          <select value={publication.kind} onChange={(e) => changeKind(e.target.value)}>
            <option value="feed">Feed · imagem única</option>
            <option value="carousel">Feed · carrossel</option>
            <option value="story">Story</option>
            <option value="reel_cover">Capa de Reel · imagem</option>
          </select>
        </label>
        <label>
          <span className="field-label">Proporção e resolução</span>
          <select
            value={publication.preset}
            onChange={(e) => setPublication({ ...publication, preset: e.target.value })}
            required
            disabled={!formats.length}
          >
            {formats
              .filter((f) => f.types.includes(publication.kind))
              .map((f) => (
                <option key={f.id} value={f.id}>
                  {f.ratio} · {f.width} × {f.height} px{f.id === 'feed_tall' ? ' · pelo app' : ''}
                </option>
              ))}
          </select>
        </label>
      </div>
      {publication.kind === 'carousel' && (
        <label className="block">
          <span className="field-label">Quantidade de cards</span>
          <select
            value={publication.slides}
            onChange={(e) => setPublication({ ...publication, slides: Number(e.target.value) })}
          >
            {Array.from({ length: 9 }, (_, i) => i + 2).map((n) => (
              <option key={n} value={n}>
                {n} cards
              </option>
            ))}
          </select>
          <p className="muted text-xs mt-2">
            Uma arte por card, na mesma proporção. Cada card gera uma chamada de imagem; cards
            concluídos são preservados se houver falha.
          </p>
        </label>
      )}
      {publication.kind === 'reel_cover' && (
        <p className="hint">
          Esta etapa produz a capa estática. A produção do vídeo de Reel ainda não está disponível.
        </p>
      )}
      {publication.preset === 'feed_tall' && (
        <p className="hint">
          3:4 é destinado à postagem manual pelo app. A compatibilidade com publicação pela API será
          validada na integração.
        </p>
      )}
      <label className="block">
        <span className="field-label">
          Produto do Brand Kit <small>opcional</small>
        </span>
        <select value={product} disabled={!!photo} onChange={(e) => setProduct(e.target.value)}>
          <option value="">Selecionar uma foto existente</option>
          {products.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      <div className="grid sm:grid-cols-2 gap-4">
        <UploadField label="Foto do produto" file={photo} onChange={setPhoto} optional />
        <UploadField label="Referência visual" file={reference} onChange={setReference} optional />
      </div>
      <p className="muted text-xs">
        {reference
          ? 'A referência enviada complementa as referências da marca nesta campanha.'
          : 'Serão usadas todas as imagens de brand/references.'}{' '}
        A foto do produto é separada: escolha uma no Brand Kit ou envie a embalagem, quando
        necessário.
      </p>
      <div className="divider" />
      <div className="flex flex-wrap justify-between gap-4 items-center">
        <label className="flex gap-3 items-center cursor-pointer">
          <input
            type="checkbox"
            checked={image && mode === 'live'}
            disabled={mode === 'demo'}
            onChange={(e) => setImage(e.target.checked)}
          />
          <span>
            <strong className="text-sm">Produzir as artes selecionadas</strong>
            <span className="muted block text-xs mt-1">
              {publication.slides} imagem(ns) no formato escolhido, após a revisão.
            </span>
          </span>
        </label>
        <label className="mode-label">
          <span className="sr-only">Modo de execução</span>
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="live">Geração com IA</option>
            <option value="demo">Demonstração sem API</option>
          </select>
        </label>
      </div>
      {mode === 'demo' ? (
        <p className="hint">
          <FlaskConical size={16} /> Respostas fixas para testar os agentes. Sem geração de imagem
          ou consumo de API.
        </p>
      ) : (
        <p className="muted text-xs">
          Usa a API OpenAI configurada no projeto. Textos e imagens consomem créditos. Tudo é salvo
          como rascunho.
        </p>
      )}
      {!configured && mode === 'live' && (
        <p className="error">Configure OPENAI_API_KEY e OPENAI_MODEL no .env antes de gerar.</p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button
        className="button primary w-full justify-center"
        disabled={sending || helping || busy || !formats.length || (mode === 'live' && !configured)}
      >
        {sending
          ? 'Iniciando…'
          : busy
            ? 'Uma campanha está em andamento'
            : initial?.id?.startsWith('run-')
              ? 'Gerar versão editada'
              : 'Criar campanha'}
        <ArrowRight size={17} />
      </button>
    </form>
  );
}
