import { useCallback, useEffect, useState } from 'react';

const currentRoute = () => window.location.pathname + window.location.search;

export function navigateRoute(path, { replace = false } = {}) {
  const previousPath = window.location.pathname;
  if (replace) window.history.replaceState({}, '', path);
  else window.history.pushState({}, '', path);
  window.dispatchEvent(new Event('studio:navigate'));
  // A new page starts at its heading. Queries, anchors and native Back/Forward
  // retain their own position instead of being treated as a fresh page visit.
  if (window.location.pathname !== previousPath && !window.location.hash) {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }
}

export function useRoute() {
  const [route, setRoute] = useState(currentRoute);

  useEffect(() => {
    const onPop = () => setRoute(currentRoute());
    window.addEventListener('popstate', onPop);
    window.addEventListener('studio:navigate', onPop);
    return () => {
      window.removeEventListener('popstate', onPop);
      window.removeEventListener('studio:navigate', onPop);
    };
  }, []);

  const navigate = useCallback(navigateRoute, []);

  return [route, navigate];
}

export function hashToken() {
  // The invite token travels in the fragment so it never reaches a server log. Clear it
  // from the address bar as soon as it is read.
  const token = window.location.hash.replace(/^#/, '');
  return token || '';
}

export function clearHash() {
  window.history.replaceState({}, '', window.location.pathname + window.location.search);
}
