import Textarea from '../../shared/components/Textarea.jsx';
import Form from '../../shared/components/Form.jsx';
import React, { useState, useEffect } from 'react';
import {
  ArrowRight,
  Sparkles,
  ImagePlus,
  FlaskConical,
  ChevronDown,
  SlidersHorizontal,
  Plus,
} from 'lucide-react';
import BriefAssistant from '../briefing/BriefAssistant.jsx';
import UploadField from '../../shared/components/UploadField.jsx';
import SearchSelect from '../../shared/components/SearchSelect.jsx';
import CampaignMediaSource from './CampaignMediaSource.jsx';
import { fileData, api, post } from '../../shared/api/client.js';
import Required from '../../shared/components/Required.jsx';
import { buildRunRequest } from './run-request.js';
import './campaign-form.css';

export default function CampaignForm({
  products = [],
  busy,
  activityBusy = false,
  configured,
  models = [],
  imageModels = [],
  onSubmit,
  onAssist,
  onProductSaved,
  initial,
}) {
  const [formats, setFormats] = useState([]);
  const [publication, setPublication] = useState(
    initial?.publication || { kind: 'feed', preset: 'feed_portrait', slides: 1 }
  );
  useEffect(() => {
    api('/api/formats')
      .then(setFormats)
      .catch((e) => setError(e.message));
  }, []);
  // The campaign should reuse what the store already uploaded, so the picker is fed by
  // the same catalog the References page shows.
  const [libraryRevision, setLibraryRevision] = useState(0);
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [libraryError, setLibraryError] = useState('');
  useEffect(() => {
    let active = true;
    setLibraryLoading(true);
    setLibraryError('');
    api('/api/references')
      .then((items) => {
        if (active) setLibrary((items || []).filter((item) => item.kind !== 'product'));
      })
      .catch((e) => {
        if (active) setLibraryError(e.message);
      })
      .finally(() => {
        if (active) setLibraryLoading(false);
      });
    return () => {
      active = false;
    };
  }, [libraryRevision]);
  async function saveProduct() {
    if (productSource !== 'upload' || !photo || savingProduct || sending || busy) return;
    setSavingProduct(true);
    setProductSaved('');
    setError('');
    try {
      const item = await post('/api/references', {
        kind: 'product',
        title: photo.name.replace(/\.[^.]+$/, ''),
        upload: await fileData(photo),
      });
      // The reference endpoint and the media picker have distinct IDs. Select the
      // refreshed media entry so the saved product remains visibly selected.
      const assets = await onProductSaved?.();
      const saved = assets?.find(
        (asset) => asset.product && asset.name === `${item.id}.${item.extension}`
      );
      const savedId = saved?.id || item.id;
      setSavedProduct({ id: savedId, title: item.title, url: saved?.url || item.url });
      setProduct(savedId);
      setProductSource('library');
      setPhoto(null);
      setProductSaved(`"${item.title}" salvo no Brand Kit e selecionado para esta campanha.`);
      setLibraryRevision((value) => value + 1);
    } catch (e) {
      setError(e.message);
    } finally {
      setSavingProduct(false);
    }
  }
  function changeKind(kind) {
    setPublication({
      kind,
      preset: kind === 'story' || kind === 'reel_cover' ? kind : 'feed_portrait',
      slides: kind === 'carousel' ? 3 : 1,
    });
  }
  const [request, setRequest] = useState(initial?.request || ''),
    [facts, setFacts] = useState(initial?.confirmed_facts?.join('\n') || ''),
    [selection, setSelection] = useState(
      initial?.mode === 'demo' ? 'demo' : initial?.model_id || ''
    );
  const mode = selection === 'demo' ? 'demo' : 'live';
  const [imageModel, setImageModel] = useState(initial?.image_model_id || '');
  function changeImageModel(modelId) {
    setImageModel(modelId);
    if (modelId === 'nvidia:black-forest-labs/flux.1-dev') {
      setPublication((current) => ({
        kind: current.kind === 'carousel' ? 'carousel' : 'feed',
        preset: 'feed_square',
        slides: current.kind === 'carousel' ? current.slides : 1,
      }));
    }
  }
  useEffect(() => {
    if (!selection && models.length)
      setSelection(models.find((m) => m.available)?.id || models[0].id);
  }, [models, selection]);
  useEffect(() => {
    if (!imageModel && imageModels.length) setImageModel(imageModels[0].id);
  }, [imageModels, imageModel]);
  const chosenImage = imageModels.find((m) => m.id === imageModel);
  // FLUX draws at most 1344 px per side, so only the square export fits it.
  const squareOnly =
    selection !== 'demo' &&
    chosenImage?.provider === 'nvidia' &&
    publication.preset !== 'feed_square';
  const [image, setImage] = useState(initial?.generate_image ?? true),
    [product, setProduct] = useState(initial?.product_id || ''),
    [photo, setPhoto] = useState(initial?.photo || null),
    [reference, setReference] = useState(initial?.reference || null),
    [referenceId, setReferenceId] = useState(initial?.reference_id || ''),
    [library, setLibrary] = useState([]),
    [savingProduct, setSavingProduct] = useState(false),
    [productSaved, setProductSaved] = useState(''),
    [helping, setHelping] = useState(false),
    [sending, setSending] = useState(false),
    [error, setError] = useState('');
  const [productSource, setProductSource] = useState(
    initial?.photo ? 'upload' : initial?.product_id ? 'library' : 'none'
  );
  const [referenceSource, setReferenceSource] = useState(
    initial?.reference ? 'upload' : initial?.reference_id ? 'library' : 'none'
  );
  const [savedProduct, setSavedProduct] = useState(null);
  const [mediaErrors, setMediaErrors] = useState({});
  function clearMediaError(field) {
    setMediaErrors((current) => ({ ...current, [field]: '' }));
  }
  const mediaDisabled = savingProduct || sending;
  const productOptions = products.map((item) => ({
    value: item.id,
    label: item.title || item.name,
    image: item.url,
  }));
  if (savedProduct && !productOptions.some((item) => item.value === savedProduct.id)) {
    productOptions.push({
      value: savedProduct.id,
      label: savedProduct.title,
      image: savedProduct.url,
    });
  }
  async function submit(e) {
    e.preventDefault();
    if (helping || sending || savingProduct || busy) return;
    setError('');
    const missingMedia = {
      product:
        productSource === 'library' && !productOptions.some((item) => item.value === product)
          ? 'Escolha um produto do Brand Kit ou selecione Sem produto.'
          : productSource === 'upload' && !photo
            ? 'Envie uma foto do produto ou selecione Sem produto.'
            : '',
      reference:
        referenceSource === 'library' && !library.some((item) => item.id === referenceId)
          ? 'Escolha uma referência salva ou selecione Só a marca.'
          : referenceSource === 'upload' && !reference
            ? 'Envie uma imagem de referência ou selecione Só a marca.'
            : '',
    };
    setMediaErrors(missingMedia);
    if (missingMedia.product || missingMedia.reference) {
      const card =
        e.currentTarget.querySelectorAll('.campaign-media-card')[missingMedia.product ? 0 : 1];
      const field =
        card?.querySelector(
          '[role="combobox"]:not(:disabled), input[type="file"]:not(:disabled)'
        ) || card?.querySelector('input:checked');
      field?.focus();
      return;
    }
    setSending(true);
    try {
      await onSubmit(
        buildRunRequest({
          request,
          facts,
          selection,
          imageModel,
          publication,
          image,
          product: productSource === 'library' ? product : '',
          upload: productSource === 'upload' && photo ? await fileData(photo) : null,
          referenceUpload:
            referenceSource === 'upload' && reference ? await fileData(reference) : null,
          referenceId: referenceSource === 'library' ? referenceId : '',
        })
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  }
  return (
    <Form noValidate onSubmit={submit} className="panel campaign-form">
      <header className="campaign-form-header grid items-center gap-5 pb-7 min-[641px]:grid-cols-[minmax(0,1fr)_minmax(240px,310px)] min-[641px]:gap-6">
        <div className="campaign-form-intro min-w-0">
          <span className="campaign-eyebrow mb-2.5 inline-flex items-center gap-2 text-xs font-semibold">
            <Sparkles size={14} aria-hidden="true" /> Estúdio de criação
          </span>
          <h2>Da sua ideia à campanha</h2>
          <p className="muted text-sm">
            Conte o que deseja divulgar. Ajuste os detalhes e crie seu rascunho.
          </p>
        </div>
        <label className="campaign-model-field min-w-0">
          <span className="field-label">Modelo de execução</span>
          <select
            disabled={busy || sending || helping}
            value={selection}
            onChange={(e) => setSelection(e.target.value)}
          >
            <optgroup label="Modelos disponíveis">
              {models.map((m) => (
                <option key={m.id} value={m.id} disabled={!m.available}>
                  {m.label}
                  {!m.available ? ' · sem chave' : ''}
                </option>
              ))}
            </optgroup>
            <option value="demo">Demonstração sem API</option>
          </select>
        </label>
      </header>
      {activityBusy && !helping && (
        <p className="hint" role="status">
          Uma consulta de briefing ou campanha está em andamento. Você pode preparar o briefing
          enquanto aguarda; a geração será liberada ao terminar.
        </p>
      )}
      {initial?.id?.startsWith('run-') && (
        <p className="hint">
          Você está editando uma campanha. Ao gerar, uma nova versão será criada e a original será
          preservada.
        </p>
      )}
      <div className="grid items-start gap-7 py-7 min-[901px]:grid-cols-[minmax(0,1fr)_minmax(240px,300px)] min-[901px]:gap-8">
        <div className="min-w-0">
          <section className="grid gap-5" aria-label="Briefing da campanha">
            <label className="block">
              <span className="field-label">
                O que vamos criar? <Required />
              </span>
              <Textarea
                className="resize-none campaign-request"
                required
                maxLength={12000}
                rows={6}
                value={request}
                onChange={(e) => setRequest(e.target.value)}
                placeholder="Crie uma campanha para o final de semana da loja. Destaque o produto em oferta com uma arte vibrante…"
              />
            </label>
            <BriefAssistant
              request={request}
              facts={facts}
              busy={busy || sending}
              configured={mode === 'live' && !!models.find((m) => m.id === selection)?.available}
              onAssist={(payload) => onAssist({ ...payload, model_id: selection })}
              onApply={(improved, confirmed) => {
                setRequest(improved);
                if (confirmed != null) setFacts(confirmed);
              }}
              onBusy={setHelping}
            />
            <details className="campaign-facts">
              <summary className="flex min-h-8 cursor-pointer list-none items-center justify-between gap-3 text-[13px] font-medium">
                <span>
                  Informações confirmadas <small>Opcional</small>
                </span>
                <ChevronDown size={16} aria-hidden="true" />
              </summary>
              <p className="muted text-xs">
                Inclua preços, condições e detalhes que precisam aparecer corretamente.
              </p>{' '}
              <label className="block">
                <span className="field-label">
                  Informações confirmadas <small>uma por linha</small>
                </span>
                <Textarea
                  className="resize-none"
                  rows={3}
                  value={facts}
                  onChange={(e) => setFacts(e.target.value)}
                />
              </label>
            </details>
          </section>
          <section
            className="campaign-references mt-7 grid gap-3 pt-6"
            aria-labelledby="campaign-references-title"
          >
            <div className="campaign-section-heading flex items-center gap-2">
              <ImagePlus size={18} aria-hidden="true" />
              <h3 id="campaign-references-title">Produto e referências</h3>
              <span className="muted text-xs">Opcional</span>
            </div>
            <CampaignMediaSource
              title="Produto"
              description="A foto do produto que você quer divulgar."
              source={productSource}
              onSourceChange={(value) => {
                setProductSource(value);
                setProductSaved('');
                clearMediaError('product');
              }}
              libraryLabel="Do Brand Kit"
              noneLabel="Sem produto"
              disabled={mediaDisabled}
            >
              {productSource === 'library' && (
                <>
                  <SearchSelect
                    label="Produto do Brand Kit"
                    value={product}
                    options={productOptions}
                    onChange={(value) => {
                      setProduct(value);
                      setProductSaved('');
                      clearMediaError('product');
                    }}
                    placeholder="Escolher um produto salvo"
                    emptyLabel="Nenhum produto encontrado."
                    disabled={mediaDisabled || !productOptions.length}
                  />
                  {!productOptions.length && (
                    <p className="muted text-xs">
                      Seu Brand Kit ainda não tem produtos. Escolha Enviar arquivo para adicionar
                      uma foto.
                    </p>
                  )}
                </>
              )}
              {productSource === 'upload' && (
                <>
                  <UploadField
                    label="Foto do produto"
                    file={photo}
                    onChange={(file) => {
                      if (!mediaDisabled) {
                        setPhoto(file);
                        setProductSaved('');
                        clearMediaError('product');
                      }
                    }}
                  />
                  <p className="muted text-xs">
                    O arquivo será usado nesta campanha. Salve no Brand Kit se quiser reutilizá-lo.
                  </p>
                  {photo && (
                    <button
                      type="button"
                      className="button small w-fit"
                      disabled={savingProduct || sending || busy}
                      onClick={saveProduct}
                    >
                      <Plus size={14} aria-hidden="true" />
                      {savingProduct ? 'Salvando…' : 'Salvar no Brand Kit'}
                    </button>
                  )}
                </>
              )}
              {mediaErrors.product && (
                <p className="error" role="alert">
                  {mediaErrors.product}
                </p>
              )}
              {productSaved && (
                <p role="status" className="text-sm text-[var(--success-text)]">
                  {productSaved}
                </p>
              )}
            </CampaignMediaSource>
            <CampaignMediaSource
              title="Referência visual"
              description="Uma imagem para orientar o estilo e a composição da arte."
              source={referenceSource}
              onSourceChange={(value) => {
                setReferenceSource(value);
                clearMediaError('reference');
              }}
              libraryLabel="Da biblioteca"
              noneLabel="Só a marca"
              disabled={mediaDisabled}
            >
              {referenceSource === 'library' && (
                <>
                  <SearchSelect
                    label="Referência salva"
                    value={referenceId}
                    options={library.map((item) => ({
                      value: item.id,
                      label: item.title,
                      image: item.url,
                      description: [
                        { feed: 'Feed', story: 'Story', youtube: 'YouTube' }[item.kind],
                        item.width && item.height ? `${item.width} × ${item.height} px` : '',
                      ]
                        .filter(Boolean)
                        .join(' · '),
                    }))}
                    onChange={(value) => {
                      setReferenceId(value);
                      clearMediaError('reference');
                    }}
                    placeholder={
                      libraryLoading ? 'Carregando referências…' : 'Escolher uma referência'
                    }
                    emptyLabel="Nenhuma referência encontrada."
                    disabled={mediaDisabled || libraryLoading || !library.length}
                  />
                  {libraryLoading ? (
                    <p className="muted text-xs" role="status">
                      Carregando a biblioteca…
                    </p>
                  ) : libraryError ? (
                    <div className="grid gap-2">
                      <p className="error" role="alert">
                        {libraryError}
                      </p>
                      <button
                        type="button"
                        className="button small w-fit"
                        onClick={() => setLibraryRevision((value) => value + 1)}
                      >
                        Tentar novamente
                      </button>
                    </div>
                  ) : !library.length ? (
                    <p className="muted text-xs">
                      Nenhuma referência salva. Escolha Enviar arquivo ou use só as referências da
                      marca.
                    </p>
                  ) : null}
                </>
              )}
              {referenceSource === 'upload' && (
                <>
                  <UploadField
                    label="Imagem de referência"
                    file={reference}
                    onChange={(file) => {
                      if (!mediaDisabled) {
                        setReference(file);
                        clearMediaError('reference');
                      }
                    }}
                  />
                  <p className="muted text-xs">Esta referência será usada apenas nesta campanha.</p>
                </>
              )}
              {mediaErrors.reference && (
                <p className="error" role="alert">
                  {mediaErrors.reference}
                </p>
              )}
            </CampaignMediaSource>
          </section>
        </div>
        <aside
          className="campaign-form-settings grid min-w-0 gap-5"
          aria-labelledby="campaign-settings-title"
        >
          <div className="campaign-section-heading flex items-center gap-2">
            <SlidersHorizontal size={17} aria-hidden="true" />
            <h3 id="campaign-settings-title">Formato e arte</h3>
          </div>
          <div className="grid gap-5 min-[641px]:max-[900px]:grid-cols-2 min-[641px]:max-[900px]:gap-x-4">
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
                      {f.ratio} · {f.width} × {f.height} px
                      {f.id === 'feed_tall' ? ' · pelo app' : ''}
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
              Esta etapa produz a capa estática. A produção do vídeo de Reel ainda não está
              disponível.
            </p>
          )}
          {publication.preset === 'feed_tall' && (
            <p className="hint">
              3:4 é destinado à postagem manual pelo app. A compatibilidade com publicação pela API
              será validada na integração.
            </p>
          )}

          <div className="campaign-art-settings grid gap-5 pt-5">
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

            {mode === 'live' && image && imageModels.length > 1 && (
              <label className="block">
                <span className="field-label">Modelo da arte</span>
                <select value={imageModel} onChange={(e) => changeImageModel(e.target.value)}>
                  {imageModels.map((m) => (
                    <option key={m.id} value={m.id} disabled={!m.available}>
                      {m.label}
                      {m.available ? '' : ' · sem chave'}
                    </option>
                  ))}
                </select>
                {chosenImage?.note && (
                  <span className="muted block text-xs mt-1">{chosenImage.note}</span>
                )}
              </label>
            )}
            {image && squareOnly && (
              <p className="error">
                {chosenImage.label} só desenha até 1344 px por lado. Escolha o formato Feed quadrado
                (1080x1080) ou volte para o modelo padrão.
              </p>
            )}
          </div>
        </aside>
      </div>
      <footer className="campaign-form-footer grid items-center gap-x-6 gap-y-4 pt-6 min-[641px]:grid-cols-[minmax(0,1fr)_auto]">
        {mode === 'demo' ? (
          <p className="hint">
            <FlaskConical size={16} /> Respostas fixas para testar os agentes. Sem geração de imagem
            ou consumo de API.
          </p>
        ) : (
          <p className="muted text-xs">
            Textos e imagens usam créditos dos modelos selecionados. A campanha será salva como
            rascunho.
          </p>
        )}
        {mode === 'live' && !models.find((m) => m.id === selection)?.available && (
          <p className="error">
            O modelo selecionado está indisponível. Escolha outro modelo ou configure a chave do
            provedor nas configurações da loja.
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button
          className="button primary w-full justify-center"
          disabled={
            sending ||
            savingProduct ||
            helping ||
            busy ||
            !formats.length ||
            (image && squareOnly) ||
            (mode === 'live' && !models.find((m) => m.id === selection)?.available)
          }
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
      </footer>
    </Form>
  );
}
