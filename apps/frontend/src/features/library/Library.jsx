import React, { useState } from 'react';
import { Download, ArrowRight, Images } from 'lucide-react';
import DeleteImageButton from './DeleteImageButton.jsx';
import Feedback from '../../shared/components/Feedback.jsx';

function Collection({ title, lead, items, onUse, onUpload, token, disabled, onDeleted, onBusy }) {
  const [limit, setLimit] = useState(24);
  return (
    <section className="library-collection" aria-label={title}>
      <header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2>
            {title} <span className="badge">{items.length}</span>
          </h2>
          {onUpload && (
            <button className="button small" type="button" onClick={onUpload}>
              <Images size={16} /> Enviar imagem de produto
            </button>
          )}
        </div>
        <p className="muted">{lead}</p>
      </header>
      {items.length ? (
        <div className="gallery">
          {items.slice(0, limit).map((item) => (
            <figure className="panel overflow-hidden" key={item.id}>
              <a href={item.url} target="_blank" rel="noreferrer">
                <img loading="lazy" src={item.url} alt={item.title || item.name} />
              </a>
              <figcaption className="p-4 space-y-3">
                <p className="text-sm break-words font-semibold">{item.title || item.name}</p>
                <div className="flex flex-wrap gap-2">
                  <a className="button small" href={item.url} download={item.name}>
                    <Download size={14} /> Baixar
                  </a>
                  {onUse && (
                    <button className="button small" type="button" onClick={() => onUse(item)}>
                      Usar na campanha <ArrowRight size={14} />
                    </button>
                  )}
                  <DeleteImageButton
                    item={item}
                    token={token}
                    disabled={disabled}
                    onDeleted={onDeleted}
                    onBusy={onBusy}
                  />
                </div>
              </figcaption>
            </figure>
          ))}
        </div>
      ) : (
        <div className="panel p-6">
          <p className="muted">Nenhuma imagem encontrada nesta seção.</p>
        </div>
      )}
      {items.length > limit && (
        <button className="button" type="button" onClick={() => setLimit((value) => value + 24)}>
          Mostrar mais imagens
        </button>
      )}
    </section>
  );
}

export default function Library({
  media,
  brandName,
  onUseProduct,
  onUploadProduct,
  token,
  busy,
  onDeleted,
}) {
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('newest');
  const [message, setMessage] = useState('');
  const [deleting, setDeleting] = useState(false);
  function deleted(item) {
    setMessage(`“${item.title || item.name}” apagada da biblioteca.`);
    onDeleted(item);
    requestAnimationFrame(() => document.getElementById('library-search')?.focus());
  }
  const filtered = media
    .filter((item) =>
      `${item.title || ''} ${item.name}`
        .toLocaleLowerCase('pt-BR')
        .includes(search.toLocaleLowerCase('pt-BR'))
    )
    .sort((a, b) =>
      sort === 'az' || sort === 'za'
        ? (sort === 'az' ? 1 : -1) *
            (a.title || a.name).localeCompare(b.title || b.name, 'pt-BR', { numeric: true }) ||
          a.id.localeCompare(b.id)
        : (sort === 'newest' ? -1 : 1) * ((a.created_at || 0) - (b.created_at || 0)) ||
          a.id.localeCompare(b.id)
    );
  const artwork = filtered.filter(
    (item) =>
      !item.product &&
      !/^product\./.test(item.name) &&
      !/^reference\./.test(item.name) &&
      !item.name.startsWith('brand-reference')
  );
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">ACERVO {brandName.toUpperCase()}</p>
          <h1>Biblioteca</h1>
          <p className="muted mt-3">Produtos do Brand Kit e artes das campanhas da sua loja.</p>
        </div>
      </div>
      <div className="library-filters">
        <label className="field-label" htmlFor="library-search">
          Buscar imagens
          <input
            id="library-search"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Nome da imagem ou produto"
          />
        </label>
        <label className="field-label" htmlFor="library-sort">
          Ordenar por
          <select id="library-sort" value={sort} onChange={(event) => setSort(event.target.value)}>
            <option value="newest">Mais recentes</option>
            <option value="oldest">Menos recentes</option>
            <option value="az">A–Z</option>
            <option value="za">Z–A</option>
          </select>
        </label>
      </div>
      {message && <Feedback tone="success">{message}</Feedback>}
      <Collection
        key={`products-${search}-${sort}`}
        title="Imagens de Produtos"
        lead="Fotos da sua loja disponíveis para compor novas campanhas."
        items={filtered.filter((item) => item.product)}
        onUse={onUseProduct}
        onUpload={onUploadProduct}
        token={token}
        disabled={busy || deleting}
        onDeleted={deleted}
        onBusy={setDeleting}
      />
      <Collection
        key={`artwork-${search}-${sort}`}
        title="Artes de campanhas"
        lead="Peças anteriores e imagens geradas no Studio."
        items={artwork}
        token={token}
        disabled={busy || deleting}
        onDeleted={deleted}
        onBusy={setDeleting}
      />
    </>
  );
}
