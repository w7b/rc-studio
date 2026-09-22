import React, { useState } from 'react';
import { UserMinus } from 'lucide-react';
import Modal from '../../shared/components/Modal.jsx';

export const ROLE_HELP = {
  DEFAULT: 'Cota reduzida',
  PAID: 'Cota cheia',
  OWNER: 'Administra a plataforma',
};

export default function StoreMembers({ tenant, roles, busy, error, onChange, onClose }) {
  const [confirmation, setConfirmation] = useState(null);
  return (
    <Modal
      title={`Acessos · ${tenant.name}`}
      onClose={onClose}
      busy={busy}
      lead="Gerencie os cargos e o acesso das pessoas desta loja."
    >
      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
      {confirmation ? (
        <section className="member-confirmation">
          <h3>{confirmation.title}</h3>
          <p className="muted">{confirmation.lead}</p>
          <div className="admin-create-actions">
            <button
              className="button"
              autoFocus
              disabled={busy}
              onClick={() => setConfirmation(null)}
            >
              Cancelar
            </button>
            <button
              className="button action-danger"
              disabled={busy}
              onClick={() =>
                onChange(confirmation.path, confirmation.payload, () => setConfirmation(null))
              }
            >
              {confirmation.label}
            </button>
          </div>
        </section>
      ) : (
        <ul className="store-access-members">
          {tenant.members.map((member) => (
            <li key={member.id}>
              <div className="admin-member">
                <strong>{member.name || member.email}</strong>
                {member.name && <span>{member.email}</span>}
              </div>
              <div className="store-member-controls">
                <label className="field-label" htmlFor={`access-role-${member.id}`}>
                  Cargo
                </label>
                <select
                  id={`access-role-${member.id}`}
                  aria-label={`Cargo de ${member.email}`}
                  value={member.role}
                  disabled={busy}
                  onChange={(event) =>
                    setConfirmation({
                      title: `Alterar o cargo de ${member.name || member.email}?`,
                      lead: `Novo cargo: ${event.target.value}. ${event.target.value === 'OWNER' ? 'Isso concede administração de toda a plataforma.' : 'As permissões serão atualizadas imediatamente.'}`,
                      label: 'Alterar cargo',
                      path: '/api/admin/memberships',
                      payload: {
                        user_id: member.id,
                        tenant_id: tenant.id,
                        role: event.target.value,
                      },
                    })
                  }
                >
                  {roles.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
                <small className="muted">{ROLE_HELP[member.role]}</small>
                <button
                  className="button action-danger"
                  disabled={busy}
                  aria-label={`Remover acesso de ${member.email}`}
                  onClick={() =>
                    setConfirmation({
                      title: `Remover o acesso de ${member.name || member.email}?`,
                      lead: `Esta pessoa deixará de acessar ${tenant.name}.`,
                      label: 'Remover acesso',
                      path: '/api/admin/memberships/revoke',
                      payload: { user_id: member.id, tenant_id: tenant.id },
                    })
                  }
                >
                  <UserMinus size={14} /> Remover acesso
                </button>
              </div>
            </li>
          ))}
          {!tenant.members.length && <li className="muted">Nenhuma pessoa com acesso ainda.</li>}
        </ul>
      )}
    </Modal>
  );
}
