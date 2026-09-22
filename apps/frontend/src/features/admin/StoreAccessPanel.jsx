import React, { useId } from 'react';
import { Plus, ShieldOff, Store, Users, X } from 'lucide-react';

export default function StoreAccessPanel({ search, onSearch, onCreate, totals, children }) {
  const title = useId();
  return (
    <section className="panel store-access-panel" aria-labelledby={title}>
      <header className="store-access-header">
        <h2 id={title} className="title-with-icon">
          <Store size={20} aria-hidden="true" /> Lojas e acessos
        </h2>
        <div className="store-access-tools">
          <label className="admin-search">
            <span className="sr-only">Buscar lojas</span>
            <input
              type="search"
              value={search}
              placeholder="Buscar por nome ou identificador"
              onChange={(event) => onSearch(event.target.value)}
            />
            {search && (
              <button
                className="button small"
                type="button"
                aria-label="Limpar busca"
                onClick={(event) => {
                  onSearch('');
                  event.currentTarget.previousElementSibling.focus();
                }}
              >
                <X size={15} />
              </button>
            )}
          </label>
          <button className="button primary" type="button" onClick={onCreate}>
            <Plus size={15} /> Nova loja
          </button>
        </div>
      </header>
      <div className="admin-totals">
        <div className="admin-total">
          <Store size={15} aria-hidden="true" />
          <strong>{totals.stores}</strong>
          <span>lojas</span>
        </div>
        <div className="admin-total">
          <Users size={15} aria-hidden="true" />
          <strong>{totals.members}</strong>
          <span>pessoas com acesso</span>
        </div>
        <div className={totals.suspended ? 'admin-total admin-total-warn' : 'admin-total'}>
          <ShieldOff size={15} aria-hidden="true" />
          <strong>{totals.suspended}</strong>
          <span>suspensas</span>
        </div>
      </div>
      {children}
    </section>
  );
}
