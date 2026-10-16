import React from 'react';
import { LogIn } from '../icons.js';
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
    <>
      <a className="public-skip-link" href="#main-content">
        Ir para o conteúdo
      </a>
      <header className="public-header grid grid-cols-[1fr_auto] items-center gap-x-5 sm:grid-cols-[auto_1fr_auto]">
        <a className="home-mark" href="/home" onClick={goToTop} aria-label="Studio AI — início">
          Studio<strong>AI</strong>
        </a>
        <nav
          aria-label="Menu principal"
          className="flex items-center justify-center gap-6 text-sm sm:justify-start sm:pl-10"
        >
          <a href={`${home ? '' : '/home'}#como-funciona`} onClick={sectionLink}>
            Como funciona
          </a>
          <a href={`${home ? '' : '/home'}#clientes`} onClick={sectionLink}>
            Clientes
          </a>
        </nav>
        <a className="button" href={signedIn ? '/studio' : '/login'}>
          <LogIn size={16} aria-hidden="true" />
          {signedIn ? 'Abrir Studio' : 'Entrar'}
        </a>
      </header>
    </>
  );
}
