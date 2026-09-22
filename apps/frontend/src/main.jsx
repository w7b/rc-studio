import React from 'react';
import { createRoot } from 'react-dom/client';
import Session from './app/Session.jsx';
import './shared/styles/tokens.css';
import './shared/styles/global.css';
import './shared/styles/platform.css';
import './app/studio-shell.css';
import './shared/styles/controls.css';
createRoot(document.getElementById('root')).render(<Session />);
