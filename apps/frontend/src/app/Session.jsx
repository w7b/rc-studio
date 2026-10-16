import React, { useCallback, useEffect, useState } from 'react';
import { LoaderCircle } from '../shared/icons.js';
import Login from '../features/auth/Login.jsx';
import Invite from '../features/auth/Invite.jsx';
import { sessionService, onSessionLost, setCsrf } from '../services/session.js';
import { useRoute } from '../shared/hooks/useRoute.js';
import { applyBrandTheme } from '../shared/brand/applyTheme.js';
import { routeRedirect } from '../shared/navigation/routes.js';

// Public visitors do not download the operational workspace; workspace routes do
// not download the public GSAP choreography until the Home is opened.
const App = React.lazy(() => import('./App.jsx'));
const Home = React.lazy(() => import('../features/home/Home.jsx'));

// Two deployments share this shell. Standalone has no database and no login, exactly as
// the studio has always run locally; shared requires a session. /api/config says which,
// so neither mode needs a build flag.
export default function Session() {
  const [route, navigate] = useRoute();
  const [state, setState] = useState({ status: 'loading' });

  const load = useCallback(async () => {
    try {
      const config = await sessionService.getConfig();
      if (!config.shared) {
        setCsrf(config.token);
        return setState({ status: 'standalone' });
      }
      const session = await sessionService.getSession();
      if (!session.authenticated) {
        setCsrf('');
        applyBrandTheme(null);
        return setState({ status: 'anonymous', providers: config.providers || [] });
      }
      setCsrf(session.csrf);
      applyBrandTheme(session.tenant.brand_color);
      document.title = `${session.tenant.name} Studio`;
      setState({ status: 'ready', session, providers: config.providers || [] });
    } catch {
      setState({ status: 'offline' });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    // A dead session must stop the 2s poll and land on the login page, instead of
    // retrying forever behind a generic connection error.
    onSessionLost(() => {
      setCsrf('');
      setState((current) =>
        current.status === 'ready'
          ? { status: 'anonymous', providers: current.providers || [] }
          : current
      );
    });
    return () => onSessionLost(null);
  }, []);

  const signedIn = useCallback(async () => {
    await load();
    navigate('/studio', { replace: true });
  }, [load, navigate]);

  const signOut = useCallback(async () => {
    try {
      await sessionService.signOut();
    } catch {
      // A failed logout still has to clear the client; the cookie may already be gone.
    }
    setCsrf('');
    applyBrandTheme(null);
    setState((current) => ({ status: 'anonymous', providers: current.providers || [] }));
    navigate('/', { replace: true });
  }, [navigate]);

  const redirect = routeRedirect(route, state.status, state.session?.role, state.session?.modules);
  useEffect(() => {
    if (redirect) navigate(redirect, { replace: true });
  }, [redirect, navigate]);

  const pathname = route.split('?')[0];
  useEffect(() => {
    if (['/', '/home', '/login'].includes(pathname)) {
      applyBrandTheme(null);
      document.title = 'Studio AI';
    } else if (state.session) {
      applyBrandTheme(state.session.tenant.brand_color);
      document.title = `${state.session.tenant.name} Studio`;
    }
  }, [pathname, state.session]);

  if (state.status === 'loading' || redirect)
    return (
      <main className="auth-shell" aria-busy="true">
        <LoaderCircle className="spin" size={24} />
      </main>
    );

  if (state.status === 'offline')
    return (
      <main className="auth-shell">
        <div className="panel auth-card">
          <h1 className="auth-title">Studio indisponível</h1>
          <p className="auth-lead">Não foi possível falar com o servidor. Tente recarregar.</p>
          <button type="button" className="button primary" onClick={load}>
            Tentar novamente
          </button>
        </div>
      </main>
    );

  if (pathname === '/convite') return <Invite onSignedIn={signedIn} />;
  if (pathname === '/' || pathname === '/home')
    return <Home signedIn={state.status !== 'anonymous'} />;
  if (pathname === '/login') return <Login providers={state.providers} onSignedIn={signedIn} />;

  return (
    <App
      session={state.status === 'ready' ? state.session : null}
      onSignedOut={state.status === 'ready' ? signOut : null}
      onAccountUpdated={load}
      route={route}
      navigate={navigate}
    />
  );
}
