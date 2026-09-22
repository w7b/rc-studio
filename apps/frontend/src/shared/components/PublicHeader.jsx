import React from 'react';
import { LogIn } from 'lucide-react';
import SpotlightCard from './SpotlightCard.jsx';
import { useRoute } from '../hooks/useRoute.js';

export default function PublicHeader({ signedIn = false }) {
  const [route, navigate] = useRoute();
  const home = ['/', '/home'].includes(route.split('?')[0]);
  function goToTop(event) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
      return;
    event.preventDefault();
    navigate('/home');
    window.scrollTo({
      top: 0,
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
        ? 'instant'
        : 'smooth',
    });
  }
  function sectionLink(event) {
    if (
      home ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return;
    event.preventDefault();
    navigate(event.currentTarget.getAttribute('href'));
  }
  return (
    <header className="public-header">
      <a className="home-mark" href="/home" onClick={goToTop} aria-label="Studio AI — início">
        Studio<strong>AI</strong>
      </a>
      <nav aria-label="Menu principal">
        <a href={`${home ? '' : '/home'}#como-funciona`} onClick={sectionLink}>
          Como funciona
        </a>
        <a href={`${home ? '' : '/home'}#clientes`} onClick={sectionLink}>
          Clientes
        </a>
      </nav>
      <SpotlightCard as="a" className="button glass-button" href={signedIn ? '/studio' : '/login'}>
        <LogIn size={16} aria-hidden="true" />
        {signedIn ? 'Abrir Studio' : 'Entrar'}
      </SpotlightCard>
    </header>
  );
}
