import React from 'react';
import { createRoot } from 'react-dom/client';
import { IconContext } from '@phosphor-icons/react';
import '@fontsource-variable/outfit';
import Session from './app/Session.jsx';
import './shared/styles/tokens.css';
import './shared/styles/global.css';
createRoot(document.getElementById('root')).render(
  <IconContext.Provider value={{ weight: 'bold' }}>
    <React.Suspense
      fallback={
        <main className="auth-shell" role="status">
          Carregando Studio…
        </main>
      }
    >
      <Session />
    </React.Suspense>
  </IconContext.Provider>
);
