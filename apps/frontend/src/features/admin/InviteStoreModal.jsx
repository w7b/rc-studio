import React, { useState } from 'react';
import Modal from '../../shared/components/Modal.jsx';
import Form from '../../shared/components/Form.jsx';
import Feedback from '../../shared/components/Feedback.jsx';

const ROLE_LABELS = {
  DEFAULT: 'Padrão · cota reduzida',
  PAID: 'Cliente · cota cheia',
  OWNER: 'Administrador da plataforma',
};

export default function InviteStoreModal({ tenant, roles, busy, error, onCreate, onClose }) {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('DEFAULT');
  return (
    <Modal
      title={`Convidar para ${tenant.name}`}
      lead="O link só poderá ser aceito pelo e-mail informado e vale por 7 dias."
      busy={busy}
      onClose={onClose}
    >
      <Form
        noValidate
        className="invite-store-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!busy) onCreate(email.trim(), role);
        }}
      >
        <label className="field-label" htmlFor="admin-invite-email">
          E-mail da pessoa
          <input
            id="admin-invite-email"
            type="email"
            required
            autoFocus
            autoComplete="email"
            maxLength={254}
            value={email}
            disabled={busy}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <div className="field-group">
          <label className="field-label" htmlFor="admin-invite-role">
            Acesso
          </label>
          <select
            id="admin-invite-role"
            value={role}
            disabled={busy}
            onChange={(event) => setRole(event.target.value)}
          >
            {roles.map((value) => (
              <option key={value} value={value}>
                {ROLE_LABELS[value] || value}
              </option>
            ))}
          </select>
        </div>
        {role === 'OWNER' && (
          <p className="field-help">
            Este acesso permite administrar todas as lojas da plataforma.
          </p>
        )}
        {error && <Feedback>{error}</Feedback>}
        <p className="field-help">Você receberá um link para copiar e compartilhar com a pessoa.</p>
        <div className="admin-create-actions">
          <button className="button primary" type="submit" disabled={busy}>
            {busy ? 'Gerando…' : 'Gerar convite'}
          </button>
          <button className="button" type="button" disabled={busy} onClick={onClose}>
            Cancelar
          </button>
        </div>
      </Form>
    </Modal>
  );
}
