import { useEffect, useRef, useState } from 'react';

export function prefersReducedMotion() {
  return (
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  );
}

// Reveals an element once it scrolls into view. IntersectionObserver rather than a scroll
// listener, so the work happens off the main thread's hot path.
export function useReveal(options = {}) {
  const ref = useRef(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    if (prefersReducedMotion()) {
      setShown(true);
      return undefined;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShown(true);
          observer.disconnect();
        }
      },
      { threshold: 0.15, rootMargin: '0px 0px -60px 0px', ...options }
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return [ref, shown];
}

// Counts up to a number when it first appears. Skipped entirely under reduced motion,
// where the final value is simply shown.
export function useCountUp(target, shown, duration = 1100) {
  const [value, setValue] = useState(prefersReducedMotion() ? target : 0);

  useEffect(() => {
    if (!shown || prefersReducedMotion()) {
      setValue(target);
      return undefined;
    }
    let frame;
    const started = performance.now();
    function step(now) {
      const progress = Math.min((now - started) / duration, 1);
      // Ease-out: the number settles instead of stopping dead.
      setValue(Math.round(target * (1 - Math.pow(1 - progress, 3))));
      if (progress < 1) frame = requestAnimationFrame(step);
    }
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, shown, duration]);

  return value;
}
