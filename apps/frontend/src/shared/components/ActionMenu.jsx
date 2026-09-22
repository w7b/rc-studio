import React, { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { MoreHorizontal } from 'lucide-react';
import Tooltip from './Tooltip.jsx';

export default function ActionMenu({ label, children, align = 'right', disabled = false }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState(null);
  const trigger = useRef(null),
    menu = useRef(null);
  const id = useId();
  const items = () => [
    ...(menu.current?.querySelectorAll('[role="menuitem"]:not(:disabled)') || []),
  ];
  function close(restore = false) {
    setOpen(false);
    if (restore) trigger.current?.focus({ preventScroll: true });
  }

  const place = useCallback(() => {
    if (!trigger.current || !menu.current) return;
    const rect = trigger.current.getBoundingClientRect();
    const { offsetWidth: width, offsetHeight: height } = menu.current;
    const left = align === 'left' ? rect.left : rect.right - width;
    setPosition({
      left: Math.max(8, Math.min(left, innerWidth - width - 8)),
      top: Math.max(
        8,
        rect.bottom + height + 8 > innerHeight ? rect.top - height - 6 : rect.bottom + 6
      ),
    });
  }, [align]);

  useLayoutEffect(() => {
    if (open) place();
    else setPosition(null);
  }, [open, place]);

  const positioned = Boolean(position);
  useLayoutEffect(() => {
    if (open && positioned) items()[0]?.focus({ preventScroll: true });
  }, [open, positioned]);

  useEffect(() => {
    if (!open) return undefined;
    function outside(event) {
      if (!trigger.current?.contains(event.target) && !menu.current?.contains(event.target))
        close();
    }
    const scroll = (event) => {
      if (!menu.current?.contains(event.target)) place();
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('focusin', outside);
    window.addEventListener('resize', place);
    window.addEventListener('scroll', scroll, true);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('focusin', outside);
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', scroll, true);
    };
  }, [open, place]);

  function keyboard(event) {
    const options = items(),
      index = options.indexOf(document.activeElement);
    if (event.key === 'Escape') {
      event.preventDefault();
      close(true);
    }
    if (event.key === 'Tab') {
      close(true);
      return;
    }
    if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      const next =
        event.key === 'Home'
          ? 0
          : event.key === 'End'
            ? options.length - 1
            : (index + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length;
      options[next]?.focus();
    }
  }

  return (
    <div className="action-dropdown">
      <Tooltip text={label}>
        <button
          ref={trigger}
          type="button"
          className="button action-trigger"
          aria-label={label}
          aria-haspopup="menu"
          aria-expanded={open}
          aria-controls={open ? id : undefined}
          disabled={disabled}
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown') {
              event.preventDefault();
              setOpen(true);
            }
          }}
          onClick={() => setOpen((value) => !value)}
        >
          <MoreHorizontal size={17} />
        </button>
      </Tooltip>
      {open &&
        createPortal(
          <div
            ref={menu}
            id={id}
            className="action-menu action-menu-portal"
            role="menu"
            aria-label={label}
            style={{ ...position, visibility: position ? 'visible' : 'hidden' }}
            onKeyDown={keyboard}
            onClick={(event) => {
              if (event.target.closest('[role="menuitem"]:not(:disabled)')) close(true);
            }}
          >
            {children}
          </div>,
          document.body
        )}
    </div>
  );
}
