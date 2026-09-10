import React, { useState } from 'react';
import { RotateCcw, Trash2, Pencil, MoreHorizontal } from 'lucide-react';

export default function CampaignActions({ run, busy, onRetry, onDelete, onEdit }) {
  const [pending, setPending] = useState(false),
    [retryConfirm, setRetryConfirm] = useState(false),
    [confirm, setConfirm] = useState(false),
    [error, setError] = useState('');
  if (run.status === 'running') return null;
  async function act(callback) {
    setPending(true);
    setError('');
    try {
      await callback(run.id);
      setConfirm(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setPending(false);
    }
  }
  const disabled = busy || pending;
  return (
    <div className="campaign-actions" onClick={(e) => e.stopPropagation()}>
      <details
        className="action-dropdown"
        onKeyDown={(e) => {
          if (e.key === 'Escape') e.currentTarget.open = false;
        }}
        onBlur={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget)) e.currentTarget.open = false;
        }}
      >
        <summary aria-label="Opções da campanha" className="button small">
          <MoreHorizontal size={19} />
        </summary>
        <div className="action-menu">
          <button className="button small" disabled={disabled} onClick={() => act(onEdit)}>
            <Pencil size={14} />
            Editar
          </button>
          {run.status !== 'completed' && (
            <button
              className="button small"
              disabled={disabled}
              onClick={() => setRetryConfirm(true)}
            >
              <RotateCcw size={14} />
              {pending ? 'Aguarde…' : 'Tentar novamente'}
            </button>
          )}
          <button
            className="button small text-red-700"
            disabled={disabled}
            onClick={() => setConfirm(true)}
          >
            <Trash2 size={14} />
            Excluir
          </button>
        </div>
      </details>
      {retryConfirm && (
        <div role="alertdialog" aria-label="Repetir campanha" className="hint block mt-3">
          <p>
            {run.outputs.campaign
              ? 'Será gerada somente uma nova imagem.'
              : 'A campanha será reiniciada do começo, incluindo os agentes já concluídos.'}{' '}
            {run.events[0]?.mode === 'demo'
              ? 'Demonstração sem cobrança de API.'
              : 'Essa ação usa a API e pode gerar novos custos.'}
          </p>
          <div className="flex gap-2 mt-3">
            <button
              className="button small"
              disabled={disabled}
              onClick={() => setRetryConfirm(false)}
            >
              Cancelar
            </button>
            <button
              className="button small"
              disabled={disabled}
              onClick={() => {
                setRetryConfirm(false);
                act(onRetry);
              }}
            >
              Confirmar nova tentativa
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
      {error && (
        <p role="alert" className="error mt-2">
          {error}
        </p>
      )}
    </div>
  );
}
