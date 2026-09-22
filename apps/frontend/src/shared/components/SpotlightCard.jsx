import React from 'react';

export function followSpotlight(card, event) {
  if (
    card.disabled ||
    event.pointerType === 'touch' ||
    !window.matchMedia('(hover: hover) and (pointer: fine)').matches ||
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
    return;
  const bounds = card.getBoundingClientRect();
  card.style.setProperty('--spotlight-x', `${event.clientX - bounds.left}px`);
  card.style.setProperty('--spotlight-y', `${event.clientY - bounds.top}px`);
  card.dataset.spotlight = 'active';
}

export default function SpotlightCard({
  as: Element = 'article',
  children,
  className = '',
  ...props
}) {
  function followPointer(event) {
    followSpotlight(event.currentTarget, event);
  }

  function clearPointer(event) {
    delete event.currentTarget.dataset.spotlight;
  }

  return (
    <Element
      {...props}
      className={`spotlight-card ${className}`}
      onPointerMove={followPointer}
      onPointerLeave={clearPointer}
      onPointerCancel={clearPointer}
    >
      {children}
    </Element>
  );
}
