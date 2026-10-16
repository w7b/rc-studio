import React, { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, Search, X } from '../icons.js';
import { overlayRoot } from './overlayRoot.js';

export default function SearchSelect({
  label,
  value,
  options,
  onChange,
  placeholder = 'Selecionar…',
  disabled = false,
  emptyLabel = 'Nenhum resultado encontrado.',
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [position, setPosition] = useState({});
  const trigger = useRef(null),
    panel = useRef(null),
    search = useRef(null);
  const id = useId();
  const selected = options.find((option) => option.value === value);
  const normalize = (text) =>
    text
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLocaleLowerCase('pt-BR');
  const visible = options.filter((option) =>
    normalize(`${option.label} ${option.description || ''}`).includes(normalize(query))
  );
  function close() {
    setOpen(false);
    trigger.current?.focus({ preventScroll: true });
  }
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const rect = trigger.current.getBoundingClientRect();
      const below = innerHeight - rect.bottom - 12;
      const above = rect.top - 12;
      const upwards = below < 240 && above > below;
      setPosition({
        left: Math.max(
          8,
          Math.min(rect.left, innerWidth - Math.min(rect.width, innerWidth - 16) - 8)
        ),
        width: Math.min(rect.width, innerWidth - 16),
        maxHeight: Math.max(96, Math.min(360, upwards ? above : below)),
        ...(upwards ? { bottom: innerHeight - rect.top + 6 } : { top: rect.bottom + 6 }),
      });
    };
    place();
    search.current?.focus();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const outside = (event) => {
      if (!panel.current?.contains(event.target) && !trigger.current?.contains(event.target))
        setOpen(false);
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('focusin', outside);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('focusin', outside);
    };
  }, [open]);
  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);
  function keyboard(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      close();
    }
    if (event.key === 'Enter' && event.target === search.current) event.preventDefault();
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    if (['Home', 'End'].includes(event.key) && event.target === search.current) return;
    event.preventDefault();
    const items = [...panel.current.querySelectorAll('[role="option"]')];
    const index = items.indexOf(document.activeElement);
    const next =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? items.length - 1
          : index < 0
            ? event.key === 'ArrowDown'
              ? 0
              : items.length - 1
            : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
    items[next]?.focus();
  }
  return (
    <div className="min-w-0 space-y-2">
      <span id={`${id}-label`} className="field-label">
        {label}
      </span>
      <button
        ref={trigger}
        type="button"
        role="combobox"
        aria-labelledby={`${id}-label ${id}-value`}
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        aria-haspopup="listbox"
        className="search-select-trigger flex w-full min-w-0 items-center justify-between gap-3 text-left"
        disabled={disabled}
        onClick={() => {
          setQuery('');
          setOpen(!open);
        }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            setQuery('');
            setOpen(true);
          }
        }}
      >
        {selected?.image && (
          <img src={selected.image} alt="" className="h-9 w-9 shrink-0 rounded-md object-contain" />
        )}
        <span className="min-w-0 flex-1">
          <span id={`${id}-value`} className="line-clamp-2 break-words">
            {selected?.label || placeholder}
          </span>
          {selected?.description && (
            <span className="muted mt-0.5 block truncate text-xs">{selected.description}</span>
          )}
        </span>
        <ChevronDown size={16} className="shrink-0" aria-hidden="true" />
      </button>
      {open &&
        createPortal(
          <div
            ref={panel}
            style={position}
            className="search-select-panel flex flex-col overflow-hidden"
            onKeyDown={keyboard}
          >
            <div className="relative shrink-0 p-2">
              <Search
                size={16}
                className="pointer-events-none absolute top-5 left-5 muted"
                aria-hidden="true"
              />
              <input
                ref={search}
                type="search"
                aria-label={`Buscar ${label.toLocaleLowerCase('pt-BR')}`}
                placeholder="Buscar por nome…"
                className="w-full pl-9! pr-12!"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
              {query && (
                <button
                  type="button"
                  className="search-select-clear"
                  aria-label="Limpar busca"
                  onClick={() => {
                    setQuery('');
                    search.current?.focus();
                  }}
                >
                  <X size={16} aria-hidden="true" />
                </button>
              )}
            </div>
            <div
              role="listbox"
              id={id}
              aria-labelledby={`${id}-label`}
              className="min-h-0 overflow-y-auto p-1"
            >
              {visible.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  role="option"
                  aria-selected={option.value === value}
                  className="search-select-option flex w-full items-center gap-3 rounded-lg p-3 text-left"
                  onClick={() => {
                    onChange(option.value);
                    close();
                  }}
                >
                  {option.image && (
                    <img
                      src={option.image}
                      loading="lazy"
                      alt=""
                      className="h-10 w-10 shrink-0 rounded-md object-contain"
                    />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="line-clamp-2 break-words text-sm">{option.label}</span>
                    {option.description && (
                      <span className="mt-1 block truncate text-xs muted">
                        {option.description}
                      </span>
                    )}
                  </span>
                  {option.value === value && (
                    <Check size={16} className="shrink-0" aria-hidden="true" />
                  )}
                </button>
              ))}
              {!visible.length && (
                <p role="status" className="p-4 text-sm muted">
                  {emptyLabel}
                </p>
              )}
            </div>
          </div>,
          overlayRoot(trigger.current)
        )}
    </div>
  );
}
