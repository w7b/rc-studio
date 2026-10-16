import React from 'react';
import { ChevronRight } from '../shared/icons.js';
import { breadcrumbsFor, STUDIO_ROUTES } from '../shared/navigation/routes.js';

export default function StudioBreadcrumbs({ page, onNavigate }) {
  const crumbs = [{ id: 'create', label: 'Marketing' }, ...breadcrumbsFor(page)];
  return (
    <nav aria-label="Caminho da página" className="breadcrumb min-w-0 text-sm">
      <ol className="flex min-w-0 flex-wrap items-center gap-y-1">
        {crumbs.map(({ id, label }, index) => (
          <li key={`${id}-${index}`} className="flex min-w-0 items-center">
            {index > 0 && (
              <ChevronRight
                size={13}
                className="mx-2 shrink-0 breadcrumb-caret"
                aria-hidden="true"
              />
            )}
            {index === crumbs.length - 1 ? (
              <span className="py-2 break-words" aria-current="page">
                {label}
              </span>
            ) : (
              <a
                href={STUDIO_ROUTES[id]}
                onClick={(event) => {
                  if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
                  event.preventDefault();
                  onNavigate(id);
                }}
              >
                {label}
              </a>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
