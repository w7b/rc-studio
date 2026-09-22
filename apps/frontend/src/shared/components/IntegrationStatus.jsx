import React from 'react';
import { CheckCircle2, CircleHelp, TriangleAlert } from 'lucide-react';

export default function IntegrationStatus({ validation }) {
  const connected = validation?.status === 'connected';
  const Icon = !validation ? CircleHelp : connected ? CheckCircle2 : TriangleAlert;
  return (
    <div className={`integration-status ${connected ? 'is-connected' : ''}`} role="status">
      <Icon size={17} aria-hidden="true" />
      <div>
        <strong>
          {!validation
            ? 'Conexão ainda não validada'
            : connected
              ? 'Leitura validada'
              : 'Conexão requer atenção'}
        </strong>
        <p>
          {validation?.message || 'Valide a conta para conferir o token e o acesso às campanhas.'}
        </p>
        {validation?.checked_at && (
          <small>
            Última verificação: {new Date(validation.checked_at).toLocaleString('pt-BR')}
          </small>
        )}
      </div>
    </div>
  );
}
