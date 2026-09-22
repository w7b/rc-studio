import React, { useId } from 'react';
import FieldHelp from '../../shared/components/FieldHelp.jsx';

export default function CampaignMediaSource({
  title,
  description,
  source,
  onSourceChange,
  libraryLabel,
  noneLabel,
  disabled,
  children,
}) {
  const id = useId();
  return (
    <fieldset
      disabled={disabled}
      aria-describedby={`${id}-description`}
      className="campaign-media-card min-w-0 rounded-[var(--control-radius)] border p-3"
    >
      <legend className="sr-only">{title} Opcional</legend>
      <p id={`${id}-description`} className="sr-only">
        {description}
      </p>
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold" aria-hidden="true">
            {title}
          </span>
          <FieldHelp text={description} />
        </div>
        <div
          className="grid w-full min-w-0 grid-cols-3 gap-1.5 sm:w-auto"
          role="group"
          aria-label={`Origem: ${title}`}
        >
          {[
            ['library', libraryLabel],
            ['upload', 'Enviar arquivo'],
            ['none', noneLabel],
          ].map(([value, label]) => (
            <label
              key={value}
              className="campaign-source-option flex min-h-9 min-w-0 cursor-pointer items-center justify-center gap-1.5 rounded-[var(--control-radius)] border px-2 py-2 text-center text-xs leading-snug sm:px-3"
            >
              <input
                type="radio"
                name={`${id}-source`}
                value={value}
                checked={source === value}
                onChange={() => onSourceChange(value)}
                className="shrink-0"
              />
              <span className="min-w-0 break-words">{label}</span>
            </label>
          ))}
        </div>
      </div>
      {source !== 'none' && <div className="mt-3 grid min-w-0 gap-3">{children}</div>}
    </fieldset>
  );
}
