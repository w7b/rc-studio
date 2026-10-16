import React, { useState } from 'react';
import { KeyRound } from '../../shared/icons.js';
import { sessionService } from '../../services/session.js';

const LABELS = { google: 'Google', microsoft: 'Microsoft', auth0: 'conta corporativa' };

// Providers are announced by the server. No client secrets or tokens enter browser storage.
export default function OAuthProviders({ providers = [], disabled = false }) {
  const [pending, setPending] = useState(null);
  const available = providers.filter((provider) => /^[a-z][a-z0-9_-]*$/.test(provider));
  if (!available.length) return null;
  return (
    <div className="oauth-providers">
      <p className="auth-divider">ou continue com sua conta</p>
      {available.map((provider) => (
        <button
          key={provider}
          type="button"
          className="button"
          disabled={disabled || Boolean(pending)}
          aria-busy={pending === provider}
          onClick={() => {
            setPending(provider);
            window.location.assign(sessionService.providerUrl(provider));
          }}
        >
          <KeyRound size={16} aria-hidden="true" />
          Entrar com {LABELS[provider] || provider}
        </button>
      ))}
    </div>
  );
}
