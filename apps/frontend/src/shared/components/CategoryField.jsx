import React, { useId } from 'react';
import { STORE_CATEGORIES } from '../catalog/storeCategories.js';

export default function CategoryField({ id, value, onChange }) {
  const list = useId();
  return (
    <label className="field-label" htmlFor={id}>
      Categoria da loja
      <input
        id={id}
        list={list}
        value={value || ''}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Selecione ou escreva outra categoria"
      />
      <datalist id={list}>
        {STORE_CATEGORIES.map((name) => (
          <option key={name} value={name} />
        ))}
      </datalist>
    </label>
  );
}
