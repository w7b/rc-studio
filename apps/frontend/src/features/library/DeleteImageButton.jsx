import React, { useRef, useState } from 'react';
import { Trash2 } from 'lucide-react';
import Modal from '../../shared/components/Modal.jsx';
import Feedback from '../../shared/components/Feedback.jsx';
import { post } from '../../shared/api/client.js';

export default function DeleteImageButton({
  item,
  source = 'media',
  token,
  disabled,
  onDeleted,
  onBusy,
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const sending = useRef(false);
  const name = item.title || item.name;
  async function remove() {
    if (sending.current || disabled) return;
    sending.current = true;
    setPending(true);
    setError('');
    onBusy?.(true);
    try {
      await post(`/api/${source}/${encodeURIComponent(item.id)}/delete`, {}, token);
      setOpen(false);
      onDeleted(item);
    } catch (failure) {
      setError(failure.message);
    } finally {
      sending.current = false;
      setPending(false);
      onBusy?.(false);
    }
  }
  return (
    <>
      <button
        type="button"
        className="button small action-danger"
        disabled={disabled || pending}
        aria-label={`Apagar ${name}`}
        onClick={() => {
          setError('');
          setOpen(true);
        }}
      >
        <Trash2 size={14} aria-hidden="true" /> Apagar
      </button>
      {open && (
        <Modal
          title="Apagar imagem?"
          onClose={() => setOpen(false)}
          busy={pending}
          lead={
            source === 'media' && !item.product
              ? 'A imagem será removida da biblioteca e da campanha de origem. Os demais arquivos da campanha permanecem.'
              : 'A imagem deixará de aparecer na biblioteca e nas opções de novas campanhas. Cópias já usadas em campanhas permanecem.'
          }
        >
          <div className="my-4 flex min-w-0 items-center gap-3">
            <img src={item.url} alt="" className="h-20 w-20 shrink-0 rounded-lg object-contain" />
            <p className="min-w-0 break-words text-sm font-medium">{name}</p>
          </div>
          <p className="muted text-xs">O arquivo ficará guardado na lixeira local da loja.</p>
          {error && <Feedback>{error}</Feedback>}
          <div className="modal-actions">
            <button
              type="button"
              className="button small"
              disabled={pending}
              onClick={() => setOpen(false)}
            >
              Cancelar
            </button>
            <button
              type="button"
              className="button small action-danger"
              disabled={pending || disabled}
              onClick={remove}
            >
              {pending ? 'Apagando…' : 'Apagar imagem'}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
