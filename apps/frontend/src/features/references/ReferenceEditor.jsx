import React, { useEffect, useRef, useState } from 'react';
import { Crop, Eraser, SlidersHorizontal, Sparkles, LoaderCircle } from '../../shared/icons.js';
import Form from '../../shared/components/Form.jsx';
import Textarea from '../../shared/components/Textarea.jsx';
import { referenceService } from '../../services/references.js';

const operations = [
  ['crop', 'Recortar', Crop],
  ['remove_background', 'Remover fundo', Eraser],
  ['enhance', 'Nitidez e tamanho', SlidersHorizontal],
  ['qwen', 'Editar com Qwen-Image-Edit', Sparkles],
];

export default function ReferenceEditor({
  items,
  selectedId,
  onSelect,
  token,
  connected,
  busy: externalBusy,
  onBusy,
  onSaved,
}) {
  const [available, setAvailable] = useState(false);
  const [operation, setOperation] = useState('crop');
  const [crop, setCrop] = useState({ x: 0, y: 0, width: 1, height: 1 });
  const [scale, setScale] = useState(1);
  const [tolerance, setTolerance] = useState(25);
  const [prompt, setPrompt] = useState('');
  const [title, setTitle] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const savingRef = useRef(false);
  const item = items.find((entry) => entry.id === selectedId);
  const busy = saving || externalBusy;
  useEffect(() => {
    let alive = true;
    setAvailable(false);
    if (connected)
      referenceService
        .getEditorOptions()
        .then((data) => {
          if (alive) setAvailable(data.qwen_available === true);
        })
        .catch(() => {
          if (alive) setAvailable(false);
        });
    return () => {
      alive = false;
    };
  }, [connected]);
  useEffect(() => {
    setCrop({ x: 0, y: 0, width: item?.width || 1, height: item?.height || 1 });
    setTitle('');
    setResult(null);
    setError('');
  }, [selectedId, item?.width, item?.height]);
  const validCrop =
    item &&
    crop.x >= 0 &&
    crop.y >= 0 &&
    crop.width > 0 &&
    crop.height > 0 &&
    crop.x + crop.width <= item.width &&
    crop.y + crop.height <= item.height;
  async function submit(event) {
    event.preventDefault();
    if (savingRef.current || busy || !item || !connected || !token) return;
    if (operation === 'crop' && !validCrop) {
      setError('Ajuste o recorte para ficar dentro dos limites da imagem.');
      return;
    }
    if (operation === 'qwen' && !available) return;
    savingRef.current = true;
    setSaving(true);
    onBusy?.(true);
    setError('');
    setResult(null);
    try {
      const saved = await referenceService.edit(
        {
          reference_id: item.id,
          operation,
          crop: operation === 'crop' ? crop : null,
          scale,
          tolerance,
          prompt,
          title,
        },
        token
      );
      setResult(saved);
      await onSaved(saved);
    } catch (failure) {
      setError(failure.message);
    } finally {
      savingRef.current = false;
      setSaving(false);
      onBusy?.(false);
    }
  }
  return (
    <section
      id="reference-editor"
      className="panel reference-editor"
      aria-labelledby="reference-editor-heading"
    >
      <header className="reference-editor-heading">
        <div>
          <h2 id="reference-editor-heading" tabIndex={-1}>
            Recortar e melhorar
          </h2>
          <p className="muted text-sm">
            Ajuste uma imagem e salve uma nova cópia. O original é preservado.
          </p>
        </div>
        <span className="badge">
          Qwen-Image-Edit · {available ? 'Configurado' : 'Não configurado'}
        </span>
      </header>
      <Form noValidate onSubmit={submit} aria-busy={saving}>
        <fieldset disabled={busy} className="reference-editor-fields">
          <label>
            <span className="field-label">Imagem para editar</span>
            <select value={selectedId} onChange={(event) => onSelect(event.target.value)}>
              <option value="">Selecione uma imagem salva</option>
              {items.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.title || 'Imagem sem nome'}
                </option>
              ))}
            </select>
          </label>
          {!items.length && <p className="hint">Importe uma imagem acima para começar.</p>}
          {item && (
            <>
              <div className="reference-editor-operations" role="group" aria-label="Tipo de edição">
                {operations.map(([value, label, Icon]) => (
                  <button
                    type="button"
                    key={value}
                    aria-pressed={operation === value}
                    disabled={value === 'qwen' && !available}
                    className={
                      'button small ' + (operation === value ? 'reference-operation-selected' : '')
                    }
                    onClick={() => {
                      setOperation(value);
                      setError('');
                      setResult(null);
                    }}
                  >
                    <Icon size={15} aria-hidden="true" />
                    {label}
                  </button>
                ))}
              </div>
              {!available && (
                <p className="muted text-xs">
                  A edição com Qwen-Image-Edit requer conexão com o modelo no servidor.
                </p>
              )}
              <div className="reference-editor-workspace">
                <div className="reference-editor-controls">
                  {operation === 'crop' && (
                    <>
                      <p className="muted text-sm">
                        Defina o enquadramento em pixels. O retângulo mostra a área que será
                        mantida.
                      </p>
                      <div className="reference-crop-fields">
                        {[
                          ['x', 'Posição X'],
                          ['y', 'Posição Y'],
                          ['width', 'Largura'],
                          ['height', 'Altura'],
                        ].map(([key, label]) => (
                          <label key={key}>
                            <span className="field-label">{label}</span>
                            <input
                              type="number"
                              required
                              step="1"
                              min={key === 'x' || key === 'y' ? 0 : 1}
                              max={key === 'x' || key === 'width' ? item.width : item.height}
                              value={crop[key]}
                              onChange={(event) =>
                                setCrop((current) => ({
                                  ...current,
                                  [key]:
                                    event.target.value === '' ? '' : Number(event.target.value),
                                }))
                              }
                            />
                          </label>
                        ))}
                      </div>
                      <p className="muted text-xs">
                        Original: {item.width} × {item.height} px.
                      </p>
                      {!validCrop && (
                        <p className="error">O recorte precisa ficar dentro da imagem.</p>
                      )}
                    </>
                  )}
                  {operation === 'remove_background' && (
                    <>
                      <p className="muted text-sm">
                        Remove um fundo uniforme e salva em PNG com transparência.
                      </p>
                      <label>
                        <span className="field-label">Tolerância de cor · {tolerance}</span>
                        <input
                          type="range"
                          min="0"
                          max="80"
                          value={tolerance}
                          onChange={(event) => setTolerance(Number(event.target.value))}
                        />
                      </label>
                      <p className="hint">
                        Funciona melhor em fundos lisos. Fundos complexos precisam de edição por IA;
                        esta ferramenta não reconhece o contorno do produto.
                      </p>
                    </>
                  )}
                  {operation === 'enhance' && (
                    <>
                      <p className="muted text-sm">
                        Ajusta a nitidez e, se necessário, amplia a imagem. Não recupera detalhes
                        ausentes no original.
                      </p>
                      <label>
                        <span className="field-label">Tamanho da cópia</span>
                        <select
                          value={scale}
                          onChange={(event) => setScale(Number(event.target.value))}
                        >
                          <option value={1}>Manter tamanho · 1×</option>
                          <option value={2}>Ampliar · 2×</option>
                        </select>
                      </label>
                    </>
                  )}
                  {operation === 'qwen' && (
                    <>
                      <label>
                        <span className="field-label">O que deseja mudar?</span>
                        <Textarea
                          className="resize-none"
                          required
                          maxLength={2000}
                          rows={4}
                          value={prompt}
                          onChange={(event) => setPrompt(event.target.value)}
                          placeholder="Ex.: isole o produto sobre um fundo branco, mantendo a embalagem."
                        />
                      </label>
                      <p className="hint">
                        A edição usa o modelo conectado no servidor. Pedir para isolar o produto não
                        garante um fundo transparente.
                      </p>
                    </>
                  )}
                  <label>
                    <span className="field-label">
                      Nome da cópia <small>opcional</small>
                    </span>
                    <input
                      maxLength={120}
                      value={title}
                      onChange={(event) => setTitle(event.target.value)}
                      placeholder={item.title || 'Imagem editada'}
                    />
                  </label>
                </div>
                <div className="reference-editor-preview">
                  <figure>
                    <figcaption>
                      Original{operation === 'crop' ? ' · prévia do recorte' : ''}
                    </figcaption>
                    <div
                      className="reference-image-frame"
                      style={{ maxWidth: Math.min(400, (320 * item.width) / item.height) }}
                    >
                      <img src={item.url} alt={'Original: ' + item.title} />
                      {operation === 'crop' && validCrop && (
                        <span
                          className="reference-crop-overlay"
                          aria-hidden="true"
                          style={{
                            left: `${(crop.x / item.width) * 100}%`,
                            top: `${(crop.y / item.height) * 100}%`,
                            width: `${(crop.width / item.width) * 100}%`,
                            height: `${(crop.height / item.height) * 100}%`,
                          }}
                        />
                      )}
                    </div>
                  </figure>
                  {result && (
                    <figure>
                      <figcaption>
                        Cópia salva · {result.width} × {result.height} px
                      </figcaption>
                      <div className="reference-image-frame">
                        <img src={result.url} alt={'Resultado: ' + result.title} />
                      </div>
                    </figure>
                  )}
                </div>
              </div>
            </>
          )}
        </fieldset>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {result && (
          <p className="hint" role="status">
            Cópia salva na coleção. A imagem original foi preservada.
          </p>
        )}
        {item && (
          <div className="reference-editor-footer">
            <p className="muted text-xs">A nova imagem ficará disponível para usar na campanha.</p>
            <button
              className="button primary"
              disabled={
                busy ||
                !connected ||
                !token ||
                (operation === 'qwen' && !available) ||
                (operation === 'crop' && !validCrop)
              }
            >
              {saving && <LoaderCircle size={16} className="animate-spin" aria-hidden="true" />}
              {saving ? 'Salvando cópia…' : 'Aplicar e salvar cópia'}
            </button>
          </div>
        )}
      </Form>
    </section>
  );
}
