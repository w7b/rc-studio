import React, { useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

export default function Tooltip({ text, children }) {
  const [position, setPosition] = useState(null);
  const anchor = useRef(null);
  const id = useId();
  const show = () => {
    const rect = anchor.current.firstElementChild.getBoundingClientRect();
    const above = rect.top > 72;
    setPosition({
      left: Math.max(12, Math.min(rect.left, innerWidth - 292)),
      ...(above ? { bottom: innerHeight - rect.top + 8 } : { top: rect.bottom + 8 }),
    });
  };
  return (
    <span
      ref={anchor}
      className="inline-flex"
      onPointerEnter={(event) => {
        if (event.pointerType !== 'touch') show();
      }}
      onPointerLeave={() => setPosition(null)}
      onFocus={show}
      onBlur={() => setPosition(null)}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && position) {
          event.stopPropagation();
          setPosition(null);
        }
      }}
    >
      {React.cloneElement(children, {
        'aria-describedby': position ? id : children.props['aria-describedby'],
      })}
      {position &&
        createPortal(
          <span id={id} role="tooltip" style={position} className="studio-tooltip">
            {text}
          </span>,
          document.body
        )}
    </span>
  );
}
