import React, { useState } from 'react';
import { Search } from 'lucide-react';
import Modal from '../../shared/components/Modal.jsx';
import { STORE_CATEGORIES } from '../../shared/catalog/storeCategories.js';

export default function StoreCategoriesModal({ value = [], onApply, onClose }) {
  const [selected, setSelected] = useState(value);
  const [search, setSearch] = useState('');
  const matches = STORE_CATEGORIES.filter((name) =>
    name.toLocaleLowerCase('pt-BR').includes(search.toLocaleLowerCase('pt-BR'))
  );
  function toggle(name) {
    setSelected((current) =>
      current.includes(name)
        ? current.filter((item) => item !== name)
        : current.length < 3
          ? [...current, name]
          : current
    );
  }
  return (
    <Modal
      title="Regras do ramo"
      lead="Selecione até 3 categorias. As regras dos ramos selecionados serão combinadas nas campanhas."
      onClose={onClose}
    >
      <label className="field-label title-with-icon" htmlFor="category-search">
        <Search size={14} aria-hidden="true" /> Buscar categoria
      </label>
      <input
        id="category-search"
        type="search"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Ex.: farmácia, petshop, padaria"
      />
      <p className="category-selection-count" role="status">
        {selected.length} de 3 selecionadas
        {selected.length === 3 ? ' · Desmarque uma para escolher outra.' : ''}
      </p>
      {selected.length > 0 && (
        <div className="category-selected" aria-label="Categorias selecionadas">
          {selected.map((name) => (
            <button
              className="button small"
              type="button"
              key={name}
              onClick={() => toggle(name)}
              aria-label={`Desmarcar ${name}`}
            >
              {name} ×
            </button>
          ))}
        </div>
      )}
      <fieldset className="category-options">
        <legend className="sr-only">Categorias de loja</legend>
        {matches.map((name) => (
          <label className="category-option" key={name}>
            <input
              type="checkbox"
              checked={selected.includes(name)}
              disabled={selected.length >= 3 && !selected.includes(name)}
              onChange={() => toggle(name)}
            />
            <span>{name}</span>
          </label>
        ))}
        {!matches.length && <p className="muted">Nenhuma categoria encontrada.</p>}
      </fieldset>
      <div className="admin-create-actions">
        <button className="button" type="button" onClick={onClose}>
          Cancelar
        </button>
        <button className="button primary" type="button" onClick={() => onApply(selected)}>
          Aplicar seleção
        </button>
      </div>
      <p className="field-help">Depois, salve os dados da loja para confirmar as alterações.</p>
    </Modal>
  );
}
