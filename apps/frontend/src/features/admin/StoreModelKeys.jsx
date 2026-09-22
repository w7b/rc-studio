import React, { useEffect, useState } from 'react';
import { KeyRound, LoaderCircle } from 'lucide-react';
import { api } from '../../shared/api/client.js';
import Modal from '../../shared/components/Modal.jsx';
import Form from '../../shared/components/Form.jsx';
import PasswordInput from '../../shared/components/PasswordInput.jsx';

export default function StoreModelKeys({ tenant, busy, error, onSave, onClose }) {
  const [state, setState] = useState(null);
  const [values, setValues] = useState({});
  const [failure, setFailure] = useState('');
  const [revision, setRevision] = useState(0);
  const [restoring, setRestoring] = useState(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    let cancelled = false;
    setFailure('');
    api(`/api/admin/tenants/model-keys?tenant_id=${tenant.id}`)
      .then((value) => {
        if (!cancelled) setState(value);
      })
      .catch((reason) => {
        if (!cancelled) setFailure(reason.message);
      });
    return () => {
      cancelled = true;
    };
  }, [tenant.id, revision]);
  function save(changes) {
    setSaved(false);
    onSave(changes, (result) => {
      setState(result);
      setValues({});
      setRestoring(null);
      setSaved(true);
    });
  }
  function submit(event) {
    event.preventDefault();
    const changes = Object.fromEntries(
      Object.entries(values)
        .filter(([, value]) => value.trim())
        .map(([provider, key]) => [provider, { action: 'replace', key: key.trim() }])
    );
    if (Object.keys(changes).length) save(changes);
  }
  return (
    <Modal
      title={`Chaves dos modelos · ${tenant.name}`}
      lead="Cadastre as chaves dos provedores para esta loja. Sem chave própria, ela usa a configuração global do servidor."
      busy={busy}
      onClose={onClose}
    >
      {(error || failure) && (
        <p className="auth-error" role="alert">
          {error || failure}
        </p>
      )}
      {saved && (
        <p className="account-done" role="status">
          Chaves atualizadas. A configuração vale para as próximas solicitações.
        </p>
      )}
      {!state ? (
        failure ? (
          <button className="button" onClick={() => setRevision((value) => value + 1)}>
            Tentar novamente
          </button>
        ) : (
          <p className="muted" role="status">
            Carregando configuração…
          </p>
        )
      ) : restoring ? (
        <section className="member-confirmation">
          <h3>Usar a configuração global de {state.providers[restoring].label}?</h3>
          <p className="muted">
            A chave própria desta loja será removida.{' '}
            {state.providers[restoring].inherited_configured
              ? 'As próximas solicitações usarão a chave global e seu saldo.'
              : 'Não há chave global configurada; os modelos deste provedor ficarão indisponíveis.'}
          </p>
          <div className="admin-create-actions">
            <button className="button" autoFocus disabled={busy} onClick={() => setRestoring(null)}>
              Cancelar
            </button>
            <button
              className="button action-danger"
              disabled={busy}
              onClick={() => save({ [restoring]: { action: 'inherit' } })}
            >
              Remover chave própria
            </button>
          </div>
        </section>
      ) : (
        <Form noValidate onSubmit={submit} className="model-key-form">
          {Object.entries(state.providers).map(([provider, info]) => (
            <section className="model-key-provider" key={provider}>
              <h3 className="title-with-icon">
                <KeyRound size={16} /> {info.label}
              </h3>
              <p className="field-help">
                {info.source === 'store'
                  ? 'Chave própria configurada'
                  : info.source === 'platform'
                    ? 'Usando a chave global do servidor'
                    : 'Nenhuma chave configurada'}
              </p>
              <label className="field-label" htmlFor={`model-key-${provider}`}>
                {info.source === 'store' ? 'Substituir chave' : 'Chave da loja'} · {info.label}
              </label>
              <PasswordInput
                id={`model-key-${provider}`}
                value={values[provider] || ''}
                maxLength={8192}
                autoComplete="off"
                spellCheck={false}
                disabled={busy}
                visibilityLabel={`chave ${info.label}`}
                placeholder="Cole uma nova chave"
                onChange={(event) => {
                  setValues((current) => ({ ...current, [provider]: event.target.value }));
                  setSaved(false);
                }}
              />
              {info.source === 'store' && (
                <button
                  className="button small"
                  type="button"
                  disabled={busy}
                  onClick={() => setRestoring(provider)}
                >
                  Usar configuração global · {info.label}
                </button>
              )}
            </section>
          ))}
          <p className="field-help">
            Chaves salvas nunca são exibidas. Campos vazios mantêm a configuração atual. As chaves
            atendem aos modelos de texto e imagem do respectivo provedor.
          </p>
          <div className="admin-create-actions">
            <button className="button" type="button" disabled={busy} onClick={onClose}>
              Fechar
            </button>
            <button
              className="button primary"
              type="submit"
              disabled={busy || !Object.values(values).some((value) => value.trim())}
            >
              {busy && <LoaderCircle className="spin" size={16} />} Salvar chaves
            </button>
          </div>
        </Form>
      )}
    </Modal>
  );
}
