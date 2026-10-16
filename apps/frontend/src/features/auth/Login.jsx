import Form from '../../shared/components/Form.jsx';
import React, { useState } from 'react';
import { LoaderCircle, LogIn } from '../../shared/icons.js';
import { sessionService } from '../../services/session.js';
import PublicHeader from '../../shared/components/PublicHeader.jsx';
import OAuthProviders from './OAuthProviders.jsx';
import PasswordInput from '../../shared/components/PasswordInput.jsx';

const REASONS = {
  oauth: 'Não foi possível concluir o login com o provedor. Tente novamente.',
  'sem-acesso': 'Sua conta não tem acesso a nenhuma loja. Peça um convite ao administrador.',
};

export default function Login({ providers = [], onSignedIn }) {
  const [email, setEmail] = useState(''),
    [password, setPassword] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(
      REASONS[new URLSearchParams(window.location.search).get('erro')] || ''
    );

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) || !password) {
      setError('Informe um e-mail válido e sua senha.');
      document.getElementById(!email.includes('@') ? 'login-email' : 'login-password')?.focus();
      return;
    }
    setBusy(true);
    setError('');
    try {
      await sessionService.signIn({ email, password });
      await onSignedIn();
    } catch (failure) {
      setError(failure.message);
      setPassword('');
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PublicHeader />
      <main id="main-content" className="auth-shell public-auth">
        <Form noValidate className="panel auth-card p-6" onSubmit={submit}>
          <h1 className="auth-title">Studio</h1>
          <p className="auth-lead">Entre para criar campanhas da sua loja.</p>

          <label className="field-label" htmlFor="login-email">
            E-mail
          </label>
          <input
            id="login-email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />

          <label className="field-label" htmlFor="login-password">
            Senha
          </label>
          <PasswordInput
            id="login-password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          {error ? (
            <p className="auth-error" role="alert">
              {error}
            </p>
          ) : null}

          <button className="button primary" type="submit" disabled={busy}>
            {busy ? <LoaderCircle className="spin" size={16} /> : <LogIn size={16} />}
            Entrar
          </button>

          <OAuthProviders providers={providers} disabled={busy} />

          <p className="auth-note">Não tem acesso? Peça um convite ao administrador da sua loja.</p>
        </Form>
      </main>
    </>
  );
}
