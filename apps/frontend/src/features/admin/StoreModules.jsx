import React from 'react';
import { Check, Megaphone } from 'lucide-react';
import Modal from '../../shared/components/Modal.jsx';
import IntegrationStatus from '../../shared/components/IntegrationStatus.jsx';

export default function StoreModules({
  tenant,
  catalog,
  busy,
  error,
  onToggle,
  onValidate,
  onClose,
}) {
  return (
    <Modal
      title={`Módulos · ${tenant.name}`}
      lead="Ative ou oculte os módulos desta loja. Desativar remove o item do menu e bloqueia o acesso pela URL e pela API."
      onClose={onClose}
      busy={busy}
    >
      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
      <div className="store-modules">
        {Object.entries(catalog).map(([id, label]) => (
          <label key={id} className="module-toggle">
            <span>
              {label}
              {['logs', 'agents'].includes(id) && <small>Acesso reservado ao administrador</small>}
            </span>
            <input
              type="checkbox"
              role="switch"
              checked={tenant.modules?.[id] !== false}
              disabled={busy}
              onChange={(event) => onToggle(id, event.target.checked)}
            />
          </label>
        ))}
      </div>
      <p className="muted module-note">
        <Check size={14} /> Minha conta permanece disponível. Trabalhos já iniciados podem concluir.
      </p>
      <section className="module-diagnostic">
        <h3 className="title-with-icon">
          <Megaphone size={17} /> Meta Ads
        </h3>
        <IntegrationStatus validation={tenant.meta_ads?.validation} />
        <button
          className="button"
          disabled={busy || tenant.modules?.meta_ads === false}
          onClick={onValidate}
        >
          Validar conexão com a Meta
        </button>
        <p className="muted">
          A validação consulta a conta e o acesso às campanhas. A publicação de anúncios ainda está
          indisponível.
        </p>
      </section>
    </Modal>
  );
}
