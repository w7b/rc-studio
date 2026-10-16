import Textarea from '../../shared/components/Textarea.jsx';
import Form from '../../shared/components/Form.jsx';
import React, { useEffect, useRef, useState } from 'react';
import { X, ImagePlus } from '../../shared/icons.js';
import UploadField from '../../shared/components/UploadField.jsx';
import { fileData } from '../../services/files.js';

export default function ImageRevision({ images, busy, onSubmit, onClose }) {
  const dialog = useRef(null),
    [base, setBase] = useState(images.at(-1)?.id || ''),
    [changes, setChanges] = useState(''),
    [reference, setReference] = useState(null),
    [sending, setSending] = useState(false),
    [error, setError] = useState('');
  useEffect(() => {
    dialog.current.showModal();
  }, []);
  const selected = images.find((image) => image.id === base);
  async function submit(event) {
    event.preventDefault();
    if (!changes.trim() || sending) return;
    setSending(true);
    setError('');
    try {
      await onSubmit({
        base_image_id: base,
        changes: changes.trim(),
        reference_upload: reference ? await fileData(reference) : null,
      });
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  }
  return (
    <dialog
      ref={dialog}
      className="brief-dialog revision-dialog panel p-6"
      aria-labelledby="revision-title"
      onCancel={(e) => {
        if (sending) e.preventDefault();
      }}
      onClose={onClose}
    >
      <Form noValidate onSubmit={submit} className="space-y-5">
        <div className="flex justify-between items-center gap-3">
          <h2 id="revision-title">Nova versão da imagem</h2>
          <button
            type="button"
            className="button small"
            aria-label="Fechar edição"
            disabled={sending}
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </div>
        <p className="muted text-sm">
          Escolha uma versão como base e descreva o que deve mudar. Você também pode enviar uma
          imagem de demonstração para orientar a edição. As versões anteriores serão preservadas.
        </p>
        <div className="revision-grid">
          <div>
            {selected && (
              <img
                src={selected.url}
                className="revision-preview"
                alt="Imagem base da nova versão"
              />
            )}
            <label className="block mt-3">
              <span className="field-label">Versão usada como base</span>
              <select value={base} disabled={sending} onChange={(e) => setBase(e.target.value)}>
                {images.map((image, index) => (
                  <option key={image.id} value={image.id}>
                    {image.name.startsWith('carousel-')
                      ? `Card ${Number(image.name.split('-')[1])} · `
                      : ''}
                    Versão {index + 1}
                  </option>
                ))}
              </select>
            </label>
            <div className="revision-versions mt-3" role="group" aria-label="Versões disponíveis">
              {images.map((image, index) => (
                <button
                  type="button"
                  key={image.id}
                  disabled={sending}
                  aria-pressed={base === image.id}
                  className={'revision-version ' + (base === image.id ? 'selected' : '')}
                  onClick={() => setBase(image.id)}
                >
                  <img src={image.url} alt={`Prévia da versão ${index + 1}`} loading="lazy" />
                  <span>
                    {image.name.startsWith('carousel-')
                      ? `Card ${Number(image.name.split('-')[1])} · `
                      : ''}
                    Versão {index + 1}
                  </span>
                </button>
              ))}
            </div>
          </div>
          <label>
            <span className="field-label">O que você quer alterar?</span>
            <Textarea
              className="resize-none"
              autoFocus
              required
              rows={7}
              maxLength={4000}
              disabled={sending}
              value={changes}
              onChange={(e) => setChanges(e.target.value)}
              placeholder="Ex.: aumente o preço, troque o fundo para azul e mantenha o produto e o logo nas posições atuais."
            />
            <span className="muted text-xs">{changes.length}/4000 caracteres</span>
          </label>
        </div>
        <fieldset disabled={sending}>
          <UploadField
            label="Imagem de demonstração"
            file={reference}
            onChange={(file) => {
              if (!sending) setReference(file);
            }}
            optional
          />
          <p className="muted text-xs mt-2">
            Referência visual para esta revisão. A arte selecionada acima continua sendo a base da
            nova versão.
          </p>
        </fieldset>
        <p className="hint">
          Gera somente uma nova imagem, sem repetir os agentes de texto. Usa a API e consome
          créditos.
        </p>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <button type="button" className="button" disabled={sending} onClick={onClose}>
            Cancelar
          </button>
          <button
            className="button primary"
            disabled={sending || busy || !changes.trim() || !selected}
          >
            <ImagePlus size={16} />
            {sending ? 'Iniciando…' : 'Gerar nova versão'}
          </button>
        </div>
      </Form>
    </dialog>
  );
}
