import React, { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { overlayRoot } from './overlayRoot.js';

export default function Tooltip({
  text,
  children,
  interactive = false,
  triggerLabel,
  triggerClassName,
}) {
  const [position, setPosition] = useState(null);
  const anchor = useRef(null);
  const tooltip = useRef(null);
  const dismissTimer = useRef(null);
  const id = useId();
  const show = () => {
    clearTimeout(dismissTimer.current);
    const element = interactive ? anchor.current : anchor.current.firstElementChild;
    const rect = element.getBoundingClientRect();
    const above = rect.top > 72;
    setPosition({
      left: Math.max(12, Math.min(rect.left, innerWidth - 292)),
      ...(above ? { bottom: innerHeight - rect.top + 8 } : { top: rect.bottom + 8 }),
    });
  };
  const dismiss = () => {
    dismissTimer.current = setTimeout(() => setPosition(null), 150);
  };
  const leave = (event) => {
    if (event.pointerType !== 'touch' && !anchor.current?.contains(document.activeElement))
      dismiss();
  };
  const visible = Boolean(position);
  useEffect(() => {
    if (!visible) return;
    const hide = () => setPosition(null);
    const outside = (event) => {
      if (!anchor.current?.contains(event.target) && !tooltip.current?.contains(event.target))
        hide();
    };
    window.addEventListener('scroll', hide, true);
    window.addEventListener('resize', hide);
    document.addEventListener('pointerdown', outside);
    return () => {
      window.removeEventListener('scroll', hide, true);
      window.removeEventListener('resize', hide);
      document.removeEventListener('pointerdown', outside);
      clearTimeout(dismissTimer.current);
    };
  }, [visible]);
  const Trigger = interactive ? 'button' : 'span';
  return (
    <Trigger
      ref={anchor}
      type={interactive ? 'button' : undefined}
      className={interactive ? triggerClassName : 'inline-flex'}
      aria-label={interactive ? triggerLabel : undefined}
      aria-describedby={interactive && position ? id : undefined}
      onPointerEnter={(event) => {
        if (event.pointerType !== 'touch') show();
      }}
      onPointerLeave={leave}
      onClick={interactive ? show : undefined}
      onFocus={show}
      onBlur={() => setPosition(null)}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && position) {
          event.stopPropagation();
          setPosition(null);
        }
      }}
    >
      {interactive
        ? children
        : React.cloneElement(children, {
            'aria-describedby':
              [children.props['aria-describedby'], position ? id : null]
                .filter(Boolean)
                .join(' ') || undefined,
          })}
      {position &&
        createPortal(
          <span
            ref={tooltip}
            id={id}
            role="tooltip"
            style={position}
            className="studio-tooltip"
            onPointerEnter={() => clearTimeout(dismissTimer.current)}
            onPointerLeave={leave}
          >
            {text}
          </span>,
          overlayRoot(anchor.current)
        )}
    </Trigger>
  );
}
