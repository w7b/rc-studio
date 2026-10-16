import React, { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from '../icons.js';

// Native <dialog>: focus trapping, Escape and the backdrop come from the platform rather
// than from hand-written key handlers that miss cases.
export default function Modal({ title, lead, onClose, children, busy = false }) {
  const dialog = useRef(null);
  const titleId = useId();
  const leadId = useId();

  useEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    if (element && !element.open) element.showModal();
    return () => {
      if (element?.open) element.close();
      document.body.style.overflow = overflow;
      if (previous?.isConnected) previous.focus({ preventScroll: true });
    };
  }, []);

  return createPortal(
    <dialog
      ref={dialog}
      className="modal"
      aria-labelledby={titleId}
      aria-describedby={lead ? leadId : undefined}
      aria-busy={busy || undefined}
      onKeyDown={(event) => {
        if (event.key === 'Escape') event.stopPropagation();
      }}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
      onClick={(event) => {
        // A click on the backdrop lands on the dialog element itself.
        if (!busy && event.target === dialog.current) onClose();
      }}
    >
      <div className="modal-card">
        <header>
          <div>
            <h2 id={titleId}>{title}</h2>
            {lead ? (
              <p className="panel-lead" id={leadId}>
                {lead}
              </p>
            ) : null}
          </div>
          <button
            className="button modal-close"
            type="button"
            aria-label="Fechar"
            onClick={onClose}
            disabled={busy}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </header>
        {children}
      </div>
    </dialog>,
    document.body
  );
}
