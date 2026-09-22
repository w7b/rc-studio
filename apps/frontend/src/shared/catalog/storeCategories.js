import categoryCatalog from '../../../../../resources/catalog/store-categories.json';

// Shared by the public animation and store forms. Custom trades remain supported.
export const STORE_CATEGORIES = categoryCatalog.map((category) => category.name);

// A representative selection for the home; forms and the headline keep the full catalog.
export const FEATURED_STORE_CATEGORIES = [
  'Supermercado',
  'Hortifruti',
  'Açougue',
  'Padaria',
  'Restaurante',
  'Cafeteria',
  'Pizzaria',
  'Farmácia',
  'Perfumaria',
  'Petshop',
  'Floricultura',
  'Loja de roupas',
  'Loja de calçados',
  'Ótica',
  'Papelaria',
  'Loja de eletrônicos',
  'Loja de móveis',
  'Material de construção',
  'Academia',
  'Salão de beleza',
];
