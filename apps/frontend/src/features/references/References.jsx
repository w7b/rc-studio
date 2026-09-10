import React, { useEffect, useState } from 'react';
import { Download, Images, Link, LoaderCircle, ArrowRight } from 'lucide-react';
import { api, post, fileData } from '../../shared/api/client.js';
import UploadField from '../../shared/components/UploadField.jsx';

const labels = { feed: 'Feed', story: 'Story', youtube: 'YouTube' };

export default function References({ token, connected, onUse }) {
  const [items, setItems] = useState([]),
    [loading, setLoading] = useState(true);
  const [mode, setMode] = useState('link'),
    [kind, setKind] = useState('feed');
  const [url, setUrl] = useState(''),
    [title, setTitle] = useState(''),
    [file, setFile] = useState(null);
  const [filter, setFilter] = useState('all'),
    [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let alive = true;
    api('/api/references')
      .then((data) => {
        if (alive) setItems(data);
      })
      .catch((e) => {
        if (alive) setError(e.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);
  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const item = await post(
        '/api/references',
        {
          kind,
          title,
          url: mode === 'link' ? url : '',
          upload: mode === 'file' && file ? await fileData(file) : null,
        },
        token
      );
      setItems((current) => [item, ...current.filter((existing) => existing.id !== item.id)]);
      setFilter('all');
      setUrl('');
      setFile(null);
      setTitle('');
      setMessage('Referência salva. Você já pode baixar ou usar na campanha.');
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function use(item) {
    setError('');
    setBusy(true);
    try {
      await onUse(item);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const visible = items.filter((item) => filter === 'all' || item.kind === filter);
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">SEU REPERTÓRIO CRIATIVO</p>
          <h1>Referências</h1>
          <p className="muted mt-3">
            Encontre uma ideia. Salve a imagem. Inspire sua próxima campanha.
          </p>
        </div>
        <span className="badge">{items.length} imagens salvas</span>
      </div>
      <form className="panel p-6 space-y-5 mb-6" onSubmit={submit}>
        <div className="tabs" role="group" aria-label="Forma de importar">
          {[
            ['link', 'Colar link'],
            ['file', 'Enviar arquivo'],
          ].map(([value, label]) => (
            <button
              type="button"
              key={value}
              disabled={busy}
              className={mode === value ? 'selected' : ''}
              onClick={() => setMode(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          <label>
            <span className="field-label">Tipo de referência</span>
            <select disabled={busy} value={kind} onChange={(e) => setKind(e.target.value)}>
              {Object.entries(labels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="field-label">
              Nome <small>opcional</small>
            </span>
            <input
              maxLength={120}
              disabled={busy}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ex.: composição para oferta de fim de semana"
            />
          </label>
        </div>
        {mode === 'link' ? (
          <label className="block">
            <span className="field-label">
              {kind === 'youtube' ? 'Link do vídeo do YouTube' : 'Link da publicação ou da imagem'}
            </span>
            <input
              type="url"
              required
              maxLength={2048}
              disabled={busy}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder={
                kind === 'youtube'
                  ? 'https://www.youtube.com/watch?v=…'
                  : 'https://www.instagram.com/p/… ou https://site.com/imagem.jpg'
              }
            />
          </label>
        ) : (
          <UploadField label="Imagem de referência" file={file} onChange={setFile} />
        )}
        <p className="muted text-xs">
          {kind === 'youtube'
            ? 'Busca a maior thumbnail disponível do vídeo.'
            : kind === 'story'
              ? 'Para Stories, envie o arquivo salvo ou o link direto da imagem. Links de Stories do Instagram exigem login.'
              : 'Importa a prévia pública do Instagram ou uma imagem por link direto. Carrosséis importam somente a capa disponível.'}{' '}
          PNG ou JPEG, até 8 MB. Se a origem bloquear o acesso, use Enviar arquivo.
        </p>
        <button
          className="button primary"
          disabled={busy || !token || !connected || (mode === 'file' && !file)}
        >
          {busy ? <LoaderCircle className="animate-spin" size={16} /> : <Link size={16} />}{' '}
          {busy ? 'Importando…' : 'Salvar referência'}
        </button>
      </form>
      {error && (
        <p className="error mb-5" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="hint mb-5" role="status">
          {message}
        </p>
      )}
      <div className="tabs" role="group" aria-label="Filtrar referências">
        {[['all', 'Todas'], ...Object.entries(labels)].map(([value, label]) => (
          <button
            key={value}
            className={filter === value ? 'selected' : ''}
            onClick={() => setFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>
      {loading ? (
        <p className="hint">Carregando referências…</p>
      ) : visible.length ? (
        <div className="gallery">
          {visible.map((item) => (
            <figure className="panel overflow-hidden" key={item.id}>
              <a href={item.url} target="_blank" rel="noreferrer">
                <img loading="lazy" src={item.url} alt={item.title} />
              </a>
              <figcaption className="p-4 space-y-3">
                <span className="badge">{labels[item.kind]}</span>
                <h2 className="text-sm break-words">{item.title}</h2>
                <p className="muted text-xs">
                  {item.width} × {item.height} px · {item.extension.toUpperCase()}
                </p>
                {item.source && (
                  <a
                    className="text-xs text-orange-700 block"
                    href={item.source}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Ver origem ↗
                  </a>
                )}
                <div className="flex flex-wrap gap-2">
                  <a
                    className="button small"
                    href={'/api/references/' + item.id + '/download'}
                    download
                  >
                    <Download size={14} /> Baixar
                  </a>
                  <button
                    className="button small"
                    disabled={busy || !connected}
                    onClick={() => use(item)}
                  >
                    Usar na campanha <ArrowRight size={14} />
                  </button>
                </div>
              </figcaption>
            </figure>
          ))}
        </div>
      ) : (
        <div className="panel p-10 text-center">
          <Images size={32} className="mx-auto mb-4 muted" />
          <h2>{items.length ? 'Nenhuma referência neste filtro' : 'Sua coleção começa aqui'}</h2>
          <p className="muted text-sm mt-2">
            Cole um link ou envie uma imagem para guardar sua primeira inspiração.
          </p>
        </div>
      )}
    </>
  );
}
