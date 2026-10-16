import React, { useEffect, useMemo, useRef, useState } from 'react';

export function advanceText(state, words) {
  if (!words.length) return { index: 0, length: 0, phase: 'hold' };
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

export function displayText(state, words, { paused = false, reduced = false } = {}) {
  if (reduced || !words.length) return 'comércio local';
  const word = words[state.index] || words[0];
  return paused ? word : word.slice(0, state.length);
}

export default function RotatingText({ words = [], paused = false }) {
  const entries = useMemo(
    () =>
      words.filter((word) => typeof word === 'string' && word.trim()).map((word) => word.trim()),
    [words]
  );
  const [state, setState] = useState(() => ({
    index: 0,
    length: entries[0]?.length || 0,
    phase: 'hold',
  }));
  const anchor = useRef(null);
  const [reduced, setReduced] = useState(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
  const [visible, setVisible] = useState(() => !document.hidden);
  const [inView, setInView] = useState(true);
  useEffect(() => {
    if (!window.IntersectionObserver || !anchor.current) return undefined;
    const observer = new window.IntersectionObserver(([entry]) => setInView(entry.isIntersecting));
    observer.observe(anchor.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const update = () => setVisible(!document.hidden);
    document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, []);
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    if (reduced || paused || !visible || !inView || !entries.length) return undefined;
    const timer = setTimeout(
      () => setState((current) => advanceText(current, entries)),
      state.phase === 'hold' ? 1800 : state.phase === 'erase' ? 32 : 78
    );
    return () => clearTimeout(timer);
  }, [state, entries, reduced, paused, visible, inView]);
  return (
    <span ref={anchor} className="rotating-text">
      <span className="sr-only">todos os segmentos do comércio local</span>
      <span aria-hidden="true">
        {displayText(state, entries, { paused, reduced })}
        <span className="typing-caret">|</span>
      </span>
    </span>
  );
}
