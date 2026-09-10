import React, { useEffect, useRef, useState } from 'react';
import { Sparkles, LoaderCircle, Check, X } from 'lucide-react';

export default function BriefAssistant({
  request,
  facts,
  busy,
  configured,
  onAssist,
  onApply,
  onBusy,
}) {
  const dialog = useRef(null);
  const [loading, setLoading] = useState(false),
    [result, setResult] = useState(null),
    [error, setError] = useState('');
  const [original, setOriginal] = useState(null);
  useEffect(() => {
    if (result && dialog.current && !dialog.current.open) dialog.current.showModal();
  }, [result]);
  const changed = original && (original.request !== request || original.facts !== facts);
  async function assist() {
    setError('');
    setResult(null);
    setLoading(true);
    onBusy(true);
    setOriginal({ request, facts });
    try {
      setResult(
        await onAssist({
          request,
          confirmed_facts: facts
            .split('\n')
            .map((value) => value.trim())
            .filter(Boolean),
        })
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
      onBusy(false);
    }
  }
  return (
    <div className="space-y-3">
      <button
        type="button"
        className="button small"
        disabled={loading || busy || !configured || !request.trim()}
        onClick={assist}
      >
        {loading ? <LoaderCircle size={15} className="animate-spin" /> : <Sparkles size={15} />}{' '}
        {loading ? 'Creative Producer está revisando…' : 'Melhorar briefing com Creative Producer'}
      </button>
      <p className="muted text-xs">
        Revisa sua ideia e aponta informações que faltam antes de criar. Usa a API configurada e
        consome créditos. {!request.trim() ? 'Escreva sua ideia acima para começar.' : ''}
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <dialog
          ref={dialog}
          className="brief-dialog panel p-6 space-y-4"
          aria-label="Sugestão do Creative Producer"
          onClose={() => setResult(null)}
        >
          <div className="flex justify-between items-center">
            <span className="badge">Revisão do briefing</span>
            <button
              type="button"
              className="button small"
              aria-label="Fechar sugestão"
              onClick={() => setResult(null)}
            >
              <X size={16} />
            </button>
          </div>
          <div>
            <p className="eyebrow">CREATIVE PRODUCER</p>
            <h2 className="mt-2">Uma versão mais clara da sua ideia</h2>
          </div>
          <p className="caption">{result.suggestion.improved_request}</p>
          {result.suggestion.changes.length > 0 && (
            <div>
              <strong className="text-sm">O que foi melhorado</strong>
              <ul className="list-disc pl-5 mt-2 text-sm muted space-y-1">
                {result.suggestion.changes.map((text, index) => (
                  <li key={index}>{text}</li>
                ))}
              </ul>
            </div>
          )}
          {result.suggestion.questions.length > 0 && (
            <div>
              <strong className="text-sm">Ainda vale esclarecer</strong>
              <ul className="list-disc pl-5 mt-2 text-sm muted space-y-1">
                {result.suggestion.questions.map((text, index) => (
                  <li key={index}>{text}</li>
                ))}
              </ul>
            </div>
          )}
          {result.usage && (
            <p className="muted text-xs">
              {result.usage.text?.total_tokens ?? 0} tokens ·{' '}
              {result.usage.total_cost_usd == null
                ? 'Custo indisponível para este modelo'
                : 'Custo estimado: US$ ' + result.usage.total_cost_usd.toFixed(4)}
            </p>
          )}
          {changed && (
            <p className="hint">
              O briefing mudou desde esta revisão. Peça uma nova sugestão para considerar suas
              alterações.
            </p>
          )}
          <div className="flex gap-2 flex-wrap">
            <button
              type="button"
              className="button primary small"
              disabled={busy || !!changed}
              onClick={() => {
                onApply(result.suggestion.improved_request);
                setResult(null);
              }}
            >
              <Check size={15} /> Aplicar sugestão
            </button>
            <button type="button" className="button small" onClick={() => setResult(null)}>
              <X size={15} /> Descartar
            </button>
          </div>
        </dialog>
      )}
    </div>
  );
}
