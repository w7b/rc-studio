import { useCallback, useEffect, useState } from 'react';

const currentRoute = () => window.location.pathname + window.location.search;

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

  const navigate = useCallback((path, { replace = false } = {}) => {
    if (replace) window.history.replaceState({}, '', path);
    else window.history.pushState({}, '', path);
    window.dispatchEvent(new Event('studio:navigate'));
  }, []);

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
