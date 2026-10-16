import Form from '../../shared/components/Form.jsx';
import React, { useState } from 'react';
import { Check, LoaderCircle } from '../../shared/icons.js';
import { accountService } from '../../services/account.js';
import PasswordInput from '../../shared/components/PasswordInput.jsx';

const MIN_PASSWORD = 8;

export default function Account({ session, onUpdated, section = 'profile' }) {
  const user = session?.user || {};
  const [name, setName] = useState(user.name || ''),
    [email, setEmail] = useState(user.email || ''),
    [phone, setPhone] = useState(user.phone || '');
  const [current, setCurrent] = useState(''),
    [password, setPassword] = useState(''),
    [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(''),
    [error, setError] = useState(''),
    [done, setDone] = useState('');

  async function saveDetails(event) {
    event.preventDefault();
    setBusy('details');
    setError('');
    setDone('');
    try {
      await accountService.updateDetails({ name, email, phone });
      setDone('Dados atualizados.');
      if (onUpdated) await onUpdated();
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy('');
    }
  }

  async function savePassword(event) {
    event.preventDefault();
    if (password !== confirmation) return setError('As senhas não coincidem.');
    if (password.length < MIN_PASSWORD)
      return setError(`A nova senha precisa de pelo menos ${MIN_PASSWORD} caracteres.`);
    setBusy('password');
    setError('');
    setDone('');
    try {
      // Changing the password ends every other session, so the server hands this one a
      // fresh token to keep working with.
      await accountService.changePassword({ current, password });
      setCurrent('');
      setPassword('');
      setConfirmation('');
      setDone('Senha alterada. As outras sessões foram encerradas.');
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy('');
    }
  }

  return (
    <section
      className="panel account-panel p-6"
      aria-label={section === 'security' ? 'Segurança' : 'Dados pessoais'}
    >
      <header>
        <h2>{section === 'security' ? 'Segurança' : 'Dados pessoais'}</h2>
        <p className="panel-lead">Alterações valem para a sua conta, não para a loja.</p>
      </header>

      {error ? (
        <p className="auth-error" role="alert">
          {error}
        </p>
      ) : null}
      {done ? (
        <p className="account-done" role="status">
          <Check size={15} /> {done}
        </p>
      ) : null}

      {section === 'profile' && (
        <Form noValidate className="account-form" onSubmit={saveDetails}>
          <label className="field-label" htmlFor="account-name">
            Nome
          </label>
          <input
            id="account-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoComplete="name"
          />

          <label className="field-label" htmlFor="account-email">
            E-mail
          </label>
          <input
            id="account-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            required
          />

          <label className="field-label" htmlFor="account-phone">
            Telefone
          </label>
          <input
            id="account-phone"
            type="tel"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder="(44) 99999-0000"
            autoComplete="tel"
          />

          <button className="button primary" type="submit" disabled={busy === 'details'}>
            {busy === 'details' ? <LoaderCircle className="spin" size={16} /> : null}
            Salvar dados
          </button>
        </Form>
      )}

      {section === 'security' && (
        <Form noValidate className="account-form" onSubmit={savePassword}>
          <h3>Trocar senha</h3>

          <label className="field-label" htmlFor="account-current">
            Senha atual
          </label>
          <PasswordInput
            id="account-current"
            visibilityLabel="senha atual"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
            autoComplete="current-password"
            required
          />

          <label className="field-label" htmlFor="account-new">
            Nova senha (mínimo de {MIN_PASSWORD} caracteres)
          </label>
          <PasswordInput
            id="account-new"
            visibilityLabel="nova senha"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            required
          />

          <label className="field-label" htmlFor="account-confirm">
            Repita a nova senha
          </label>
          <PasswordInput
            id="account-confirm"
            visibilityLabel="confirmação da nova senha"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
            autoComplete="new-password"
            required
          />

          <button className="button primary" type="submit" disabled={busy === 'password'}>
            {busy === 'password' ? <LoaderCircle className="spin" size={16} /> : null}
            Trocar senha
          </button>
        </Form>
      )}
    </section>
  );
}
