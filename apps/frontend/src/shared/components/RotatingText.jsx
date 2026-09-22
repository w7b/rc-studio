import React, { useEffect, useState } from 'react';

export function advanceText(state, words) {
  const word = words[state.index] || '';
  if (state.phase === 'hold') return { ...state, phase: 'erase' };
  if (state.phase === 'erase')
    return state.length > 0
      ? { ...state, length: state.length - 1 }
      : { index: (state.index + 1) % words.length, length: 0, phase: 'type' };
  return state.length < word.length
    ? { ...state, length: state.length + 1 }
    : { ...state, phase: 'hold' };
}

export default function RotatingText({ words }) {
  const [state, setState] = useState({ index: 0, length: 0, phase: 'type' });
  const [reduced, setReduced] = useState(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    if (reduced || !words.length) return undefined;
    const timer = setTimeout(
      () => setState((current) => advanceText(current, words)),
      state.phase === 'hold' ? 1800 : state.phase === 'erase' ? 32 : 78
    );
    return () => clearTimeout(timer);
  }, [state, words, reduced]);
  return (
    <span className="rotating-text">
      <span className="sr-only">todos os segmentos do comércio local</span>
      <span aria-hidden="true">
        {reduced ? 'comércio local' : words[state.index]?.slice(0, state.length)}
        <span className="typing-caret">|</span>
      </span>
    </span>
  );
}
