import Form from '../../shared/components/Form.jsx';
import React, { useState } from 'react';
import { LoaderCircle, UserPlus } from 'lucide-react';
import { post } from '../../shared/api/client.js';
import { clearHash, hashToken } from '../../shared/hooks/useRoute.js';
import PasswordInput from '../../shared/components/PasswordInput.jsx';

const MIN_PASSWORD = 8;

export default function Invite({ onSignedIn }) {
  const [token] = useState(hashToken);
  const [name, setName] = useState(''),
    [email, setEmail] = useState(''),
    [password, setPassword] = useState(''),
    [confirmation, setConfirmation] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    if (password !== confirmation) {
      setError('As senhas não coincidem.');
      document.getElementById('invite-confirmation')?.focus();
      return;
    }
    setBusy(true);
    setError('');
    try {
      await post('/api/invites/accept', {
        token,
        email: email.trim(),
        password,
        name: name.trim(),
      });
      clearHash();
      await onSignedIn();
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <main className="auth-shell">
        <div className="panel auth-card p-6">
          <h1 className="auth-title">Convite inválido</h1>
          <p className="auth-lead">
            O link do convite está incompleto. Peça um novo ao administrador da loja.
          </p>
          <a className="button" href="/login">
            Ir para o login
          </a>
        </div>
      </main>
    );
  }

  return (
    <main className="auth-shell">
      <Form noValidate className="panel auth-card p-6" onSubmit={submit}>
        <h1 className="auth-title">Aceitar convite</h1>
        <p className="auth-lead">
          Informe seus dados para acessar o Studio da loja que convidou você.
        </p>

        <label className="field-label" htmlFor="invite-email">
          E-mail do convite
        </label>
        <input
          id="invite-email"
          type="email"
          autoComplete="email"
          required
          maxLength={254}
          value={email}
          disabled={busy}
          onChange={(event) => setEmail(event.target.value)}
        />

        <label className="field-label" htmlFor="invite-name">
          Seu nome
        </label>
        <input
          id="invite-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          autoComplete="name"
          disabled={busy}
        />

        <label className="field-label" htmlFor="invite-password">
          Senha
        </label>
        <PasswordInput
          id="invite-password"
          autoComplete="new-password"
          aria-describedby="invite-password-help"
          disabled={busy}
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <p id="invite-password-help" className="field-help">
          Nova conta: crie uma senha com pelo menos {MIN_PASSWORD} caracteres. Se já tem conta, use
          sua senha atual.
        </p>

        <label className="field-label" htmlFor="invite-confirmation">
          Repita a senha
        </label>
        <PasswordInput
          id="invite-confirmation"
          visibilityLabel="confirmação da senha"
          autoComplete="new-password"
          disabled={busy}
          required
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
        />

        {error ? (
          <p className="auth-error" role="alert">
            {error}
          </p>
        ) : null}

        <button className="button primary" type="submit" disabled={busy}>
          {busy ? <LoaderCircle className="spin" size={16} /> : <UserPlus size={16} />}
          Aceitar convite
        </button>
      </Form>
    </main>
  );
}
