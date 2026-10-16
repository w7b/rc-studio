import React, { useState } from 'react';
import { RotateCcw, Trash2, Pencil, Type, TriangleAlert } from '../../shared/icons.js';
import ActionMenu from '../../shared/components/ActionMenu.jsx';
import Modal from '../../shared/components/Modal.jsx';
import Feedback from '../../shared/components/Feedback.jsx';

export default function CampaignActions({ run, busy, onRetry, onDelete, onEdit, onRename }) {
  const [pending, setPending] = useState(false),
    [retryConfirm, setRetryConfirm] = useState(false),
    [confirm, setConfirm] = useState(false),
    [renaming, setRenaming] = useState(false),
    [title, setTitle] = useState(''),
    [error, setError] = useState('');
  if (run.status === 'running') return null;
  const currentTitle =
    run.title || run.outputs?.brief?.request || run.outputs?.campaign?.brief?.request || '';
  async function act(callback) {
    setPending(true);
    setError('');
    try {
      await callback(run.id);
      setConfirm(false);
      setRetryConfirm(false);
      setRenaming(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setPending(false);
    }
  }
  const disabled = busy || pending;
  return (
    <div className="campaign-actions" onClick={(e) => e.stopPropagation()}>
      <ActionMenu label="Opções da campanha" disabled={disabled}>
        <button
          role="menuitem"
          className="button small"
          disabled={disabled}
          onClick={() => {
            setTitle(currentTitle);
            setRenaming(true);
          }}
        >
          <Type size={14} />
          Renomear campanha
        </button>
        <button
          role="menuitem"
          className="button small"
          disabled={disabled}
          onClick={() => act(onEdit)}
        >
          <Pencil size={14} />
          Editar
        </button>
        {run.status !== 'completed' && (
          <button
            role="menuitem"
            className="button small"
            disabled={disabled}
            onClick={() => {
              setError('');
              setRetryConfirm(true);
            }}
          >
            <RotateCcw size={14} />
            {pending ? 'Aguarde…' : 'Tentar novamente'}
          </button>
        )}
        <button
          role="menuitem"
          className="button small text-red-700"
          disabled={disabled}
          onClick={() => setConfirm(true)}
        >
          <Trash2 size={14} />
          Excluir
        </button>
      </ActionMenu>
      {retryConfirm && (
        <Modal title="Tentar novamente?" onClose={() => setRetryConfirm(false)} busy={pending}>
          <Feedback tone="warning">
            <TriangleAlert size={20} aria-hidden="true" />
            <span>
              {run.outputs?.campaign
                ? 'Será gerada somente uma nova imagem.'
                : 'A campanha será reiniciada do começo, incluindo os agentes já concluídos.'}{' '}
              {run.events?.[0]?.mode === 'demo'
                ? 'Demonstração sem cobrança de API.'
                : 'Essa ação usa a API e pode gerar novos custos.'}
            </span>
          </Feedback>
          {error && <Feedback>{error}</Feedback>}
          <div className="modal-actions">
            <button
              className="button small"
              disabled={pending}
              onClick={() => setRetryConfirm(false)}
            >
              Cancelar
            </button>
            <button
              className="button small warning"
              disabled={disabled}
              onClick={() => act(onRetry)}
            >
              {pending ? 'Enviando…' : 'Confirmar nova tentativa'}
            </button>
          </div>
        </Modal>
      )}
      {renaming && (
        <div role="dialog" aria-label="Renomear campanha" className="campaign-rename">
          <label className="block">
            <span className="field-label">Nome da campanha</span>
            <input
              autoFocus
              maxLength={120}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape') setRenaming(false);
                if (e.key === 'Enter' && title.trim()) {
                  e.preventDefault();
                  act(() => onRename(run.id, title.trim()));
                }
              }}
            />
          </label>
          <p className="muted text-xs">
            Só muda como a campanha aparece na lista. O briefing e os arquivos não são alterados.
          </p>
          <div className="flex gap-2 mt-3">
            <button className="button small" disabled={disabled} onClick={() => setRenaming(false)}>
              Cancelar
            </button>
            <button
              className="button small primary"
              disabled={disabled || !title.trim()}
              onClick={() => act(() => onRename(run.id, title.trim()))}
            >
              Salvar nome
            </button>
          </div>
        </div>
      )}
      {confirm && (
        <div
          role="alertdialog"
          aria-label="Excluir campanha"
          className="mt-3 p-3 rounded-lg bg-red-50 text-sm"
        >
          <p>
            Excluir esta campanha do histórico e da biblioteca? Os arquivos ficam na lixeira local.
          </p>
          <div className="flex gap-2 mt-3">
            <button className="button small" disabled={disabled} onClick={() => setConfirm(false)}>
              Cancelar
            </button>
            <button
              className="button small text-red-700"
              disabled={disabled}
              onClick={() => act(onDelete)}
            >
              Confirmar exclusão
            </button>
          </div>
        </div>
      )}
      {error && !retryConfirm && (
        <p role="alert" className="error mt-2">
          {error}
        </p>
      )}
    </div>
  );
}
