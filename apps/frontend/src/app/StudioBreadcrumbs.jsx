import React from 'react';
import { ChevronRight } from 'lucide-react';
import { breadcrumbsFor, STUDIO_ROUTES } from '../shared/navigation/routes.js';

export default function StudioBreadcrumbs({ page, onNavigate }) {
  const crumbs = [{ id: 'create', label: 'Marketing' }, ...breadcrumbsFor(page)];
  return (
    <nav
      aria-label="Caminho da página"
      className="breadcrumb flex min-w-0 flex-wrap items-center gap-y-1 text-sm"
    >
      {crumbs.map(({ id, label }, index) => (
        <React.Fragment key={`${id}-${index}`}>
          {index > 0 && (
            <ChevronRight size={13} className="mx-2 shrink-0 breadcrumb-caret" aria-hidden="true" />
          )}
          {index === crumbs.length - 1 ? (
            <span aria-current="page">{label}</span>
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
        </React.Fragment>
      ))}
    </nav>
  );
}
