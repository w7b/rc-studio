import React from 'react';
import { Download, AlertTriangle } from 'lucide-react';

const roles = {
  social_media: 'Social Media',
  copywriter: 'Copywriter',
  creative: 'Creative Producer',
  marketing_director: 'Director',
  campaign: 'Campanha consolidada',
};
export default function Diagnostics({ run }) {
  const data = run.diagnostics;
  if (!data) return null;
  const usage = data.usage?.text;
  return (
    <section className="panel p-6 space-y-4" aria-label="Diagnóstico da execução">
      <div className="flex justify-between items-center gap-3 flex-wrap">
        <h2 className="flex items-center gap-2">
          <AlertTriangle size={20} />
          Diagnóstico da execução
        </h2>
        <a className="button small" href={`/api/runs/${run.id}/files/diagnostics.json`} download>
          <Download size={15} />
          Baixar diagnóstico JSON
        </a>
      </div>
      <p className="text-sm">
        {data.recovered ? 'Corrigido automaticamente · ' : ''}
        {data.agent || 'Equipe'} · <strong>{data.error_type}</strong> ·{' '}
        {new Date(data.time).toLocaleString('pt-BR')}
      </p>
      <p className="muted text-xs break-all">
        Execução: {data.run_id} · Modelo: {data.model || 'não registrado'}
        {data.schema ? ' · Formato esperado: ' + data.schema : ''}
      </p>
      {data.historical_note && <p className="hint">{data.historical_note}</p>}
      {!!data.validation_errors.length && (
        <div className="space-y-2">
          <h3 className="font-semibold text-sm">Campos que falharam na validação</h3>
          {data.validation_errors.map((issue, index) => (
            <div className="nested text-sm" key={index}>
              <strong>
                {issue.location.length ? issue.location.join('.') : 'Regra geral da entrega'}
              </strong>
              <p>{issue.explanation || issue.type}</p>
              <code className="muted text-xs">{issue.type}</code>
            </div>
          ))}
        </div>
      )}
      <div className="hint block">
        <p>
          {usage
            ? `${usage.total_tokens.toLocaleString('pt-BR')} tokens registrados · ${data.usage.total_cost_usd == null ? 'Custo indisponível' : 'US$ ' + data.usage.total_cost_usd.toFixed(4) + ' estimados'}`
            : 'Consumo não registrado nesta execução.'}
        </p>
        <p className="mt-2">
          O erro não desfaz as chamadas já realizadas. Este valor é a estimativa da execução
          inteira, não um valor de reembolso. Confira a cobrança efetiva no painel da API.
        </p>
      </div>
      <div>
        <h3 className="font-semibold text-sm mb-2">Entregas preservadas</h3>
        <div className="flex flex-wrap gap-2">
          {data.saved_outputs.length ? (
            data.saved_outputs.map((role) => (
              <a
                key={role}
                className="button small"
                href={`/api/runs/${run.id}/files/${role}.json`}
                download
              >
                <Download size={14} />
                {roles[role] || role}
              </a>
            ))
          ) : (
            <p className="muted text-sm">Nenhuma entrega validada foi salva.</p>
          )}
        </div>
      </div>
      <p className="text-sm">{data.guidance}</p>
      {!data.recovered && (
        <p className="error">
          {data.retry_scope === 'image_only'
            ? 'Tentar novamente gera somente a imagem; os textos são reutilizados.'
            : 'Tentar novamente reinicia a campanha inteira. A retomada a partir do agente que falhou ainda não está disponível.'}{' '}
          A repetição em modo real pode gerar novos custos.
        </p>
      )}
      <details>
        <summary className="text-sm cursor-pointer font-semibold">
          Detalhes técnicos e eventos da falha
        </summary>
        <div className="mt-3 space-y-3">
          <p className="muted text-xs break-all">
            Request ID: {data.request_id || 'não registrado'} · Response ID:{' '}
            {data.response_id || 'não registrado'} · HTTP: {data.http_status || 'não registrado'}
          </p>
          <pre className="text-xs whitespace-pre-wrap break-all bg-slate-50 p-4 rounded-lg max-h-80 overflow-auto">
            {JSON.stringify(
              {
                exception_chain: data.exception_chain,
                stack: data.stack,
                response_summary: data.response_summary,
                events: data.failure_events,
              },
              null,
              2
            )}
          </pre>
          <p className="muted text-xs">
            Registra estrutura e pontos de falha, sem chaves de API, prompts ou respostas brutas.
          </p>
        </div>
      </details>
    </section>
  );
}
