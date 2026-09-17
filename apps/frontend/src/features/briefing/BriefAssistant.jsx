import React, { useEffect, useRef, useState } from 'react';
import { Sparkles, LoaderCircle, Check, X, HelpCircle } from 'lucide-react';

/** An answered question becomes a confirmed fact: the same channel the agents already
 *  treat as authoritative, so the next pass fills the gap instead of inventing it. */
function asFact(question, answer) {
  const clean = question.trim();
  return `${clean}${/[?:.]$/.test(clean) ? '' : ':'} ${answer.trim()}`;
}

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
  // Answers typed in this round, and every answer confirmed so far.
  const [answers, setAnswers] = useState({});
  const [extra, setExtra] = useState([]);
  useEffect(() => {
    if (result && dialog.current && !dialog.current.open) dialog.current.showModal();
  }, [result]);
  const changed = original && (original.request !== request || original.facts !== facts);
  const baseFacts = facts
    .split('\n')
    .map((value) => value.trim())
    .filter(Boolean);

  async function assist(extraFacts, { fresh } = {}) {
    setError('');
    if (fresh) {
      setResult(null);
      setExtra([]);
      setOriginal({ request, facts });
    }
    setAnswers({});
    setLoading(true);
    onBusy(true);
    try {
      setResult(
        await onAssist({
          request,
          confirmed_facts: [...baseFacts, ...extraFacts].slice(0, 100),
        })
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
      onBusy(false);
    }
  }

  const questions = result?.suggestion.questions || [];
  const answered = questions
    .map((question, index) => (answers[index]?.trim() ? asFact(question, answers[index]) : null))
    .filter(Boolean);

  function refine() {
    const merged = [...extra, ...answered];
    setExtra(merged);
    assist(merged);
  }

  return (
    <div className="space-y-3">
      <button
        type="button"
        className="button small"
        disabled={loading || busy || !configured || !request.trim()}
        onClick={() => assist([], { fresh: true })}
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
          {extra.length > 0 && (
            <div>
              <strong className="text-sm">Respostas já registradas</strong>
              <ul className="list-disc pl-5 mt-2 text-sm muted space-y-1">
                {extra.map((text, index) => (
                  <li key={index}>{text}</li>
                ))}
              </ul>
            </div>
          )}
          {questions.length > 0 && (
            <div className="space-y-3">
              <div>
                <strong className="text-sm">Ainda vale esclarecer</strong>
                <p className="muted text-xs mt-1">
                  Responda o que souber. Cada resposta entra como informação confirmada e o Creative
                  Producer reescreve o briefing sem essa lacuna. Deixe em branco o que ainda não
                  estiver definido — nada é inventado.
                </p>
              </div>
              {questions.map((question, index) => (
                <label className="block nested" key={index}>
                  <span className="field-label flex items-start gap-2">
                    <HelpCircle size={14} className="shrink-0 mt-[3px]" />
                    {question}
                  </span>
                  <input
                    type="text"
                    maxLength={1000}
                    value={answers[index] || ''}
                    placeholder="Sua resposta"
                    disabled={loading}
                    onChange={(e) => setAnswers({ ...answers, [index]: e.target.value })}
                    onKeyDown={(e) => {
                      // This dialog lives inside the campaign form; Enter must not submit it.
                      if (e.key !== 'Enter') return;
                      e.preventDefault();
                      if (answered.length && !changed) refine();
                    }}
                  />
                </label>
              ))}
              <button
                type="button"
                className="button small"
                disabled={loading || busy || !answered.length || !!changed}
                onClick={refine}
              >
                {loading ? (
                  <LoaderCircle size={15} className="animate-spin" />
                ) : (
                  <Sparkles size={15} />
                )}{' '}
                {loading
                  ? 'Reescrevendo com suas respostas…'
                  : `Responder e revisar (${answered.length})`}
              </button>
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
              disabled={busy || loading || !!changed}
              onClick={() => {
                onApply(
                  result.suggestion.improved_request,
                  [...baseFacts, ...extra, ...answered].join('\n')
                );
                setResult(null);
              }}
            >
              <Check size={15} /> Aplicar sugestão
              {extra.length + answered.length > 0
                ? ` e ${extra.length + answered.length} informação(ões)`
                : ''}
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
