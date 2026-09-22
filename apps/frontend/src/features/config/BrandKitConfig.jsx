import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Check, FileText, LoaderCircle, RotateCcw, Save } from 'lucide-react';
import { api, post } from '../../shared/api/client.js';

// The Brand Kit is what the agents read on every request. A store without one cannot run
// a campaign at all — load_brand refuses before any model is called — so this screen
// exists to make sure no store is ever in that state, and to let the text be edited
// without touching files on a server.
export default function BrandKitConfig() {
  const [state, setState] = useState(null),
    [drafts, setDrafts] = useState({}),
    [open, setOpen] = useState(null),
    [busy, setBusy] = useState(''),
    [error, setError] = useState(''),
    [saved, setSaved] = useState('');

  const load = useCallback(async () => {
    try {
      const value = await api('/api/brandkit');
      setState(value);
      setDrafts(Object.fromEntries(value.files.map((file) => [file.name, file.content])));
      setError('');
    } catch (failure) {
      setError(failure.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function apply(value) {
    setState(value);
    setDrafts(Object.fromEntries(value.files.map((file) => [file.name, file.content])));
  }

  async function run(key, action) {
    setBusy(key);
    setError('');
    setSaved('');
    try {
      apply(await action());
      setSaved(key);
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy('');
    }
  }

  if (!state)
    return (
      <div className="panel p-6">
        {error ? (
          <p className="auth-error" role="alert">
            {error}
          </p>
        ) : (
          <p className="muted">Carregando…</p>
        )}
      </div>
    );

  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">CONFIGURAÇÕES</p>
          <h1>Brand Kit</h1>
          <p className="muted mt-3">
            É isto que os agentes leem antes de escrever qualquer campanha. Comece pela base e
            ajuste só o que muda na identidade da sua loja.
          </p>
        </div>
        <button
          className="button"
          type="button"
          disabled={Boolean(busy)}
          onClick={() => run('seed', () => post('/api/brandkit/seed', {}))}
        >
          {busy === 'seed' ? <LoaderCircle className="spin" size={15} /> : <FileText size={15} />}
          Criar o que falta
        </button>
      </div>

      {error ? (
        <p className="auth-error" role="alert">
          {error}
        </p>
      ) : null}

      {!state.complete ? (
        <p className="kit-warning" role="alert">
          <AlertTriangle size={16} aria-hidden="true" />
          Faltam arquivos no Brand Kit. Enquanto faltar, nenhuma campanha desta loja roda — use
          “Criar o que falta” para gerar a base.
        </p>
      ) : null}

      {state.extras?.length ? (
        <p className="muted kit-extras">
          Arquivos extras que os agentes também leem: {state.extras.join(', ')}.
        </p>
      ) : null}

      <div className="panel kit-files">
        {state.files.map((file) => {
          const dirty = drafts[file.name] !== file.content;
          return (
            <section className="kit-file" key={file.name}>
              <header>
                <button
                  type="button"
                  className="kit-toggle"
                  aria-expanded={open === file.name}
                  onClick={() => setOpen(open === file.name ? null : file.name)}
                >
                  <FileText size={15} aria-hidden="true" />
                  <span>
                    <strong>{file.title}</strong>
                    <small>{file.hint}</small>
                  </span>
                </button>
                <div className="kit-state">
                  {!file.exists ? (
                    <span className="kit-missing">Faltando</span>
                  ) : dirty ? (
                    <span className="kit-dirty">Editado</span>
                  ) : saved === file.name ? (
                    <span className="kit-ok">
                      <Check size={13} /> Salvo
                    </span>
                  ) : null}
                  <code>{file.name}</code>
                </div>
              </header>

              {open === file.name ? (
                <div className="kit-editor">
                  <label className="sr-only" htmlFor={`kit-${file.name}`}>
                    Conteúdo de {file.title}
                  </label>
                  <textarea
                    id={`kit-${file.name}`}
                    value={drafts[file.name] ?? ''}
                    spellCheck="false"
                    onChange={(event) => setDrafts({ ...drafts, [file.name]: event.target.value })}
                  />
                  <div className="kit-actions">
                    <button
                      className="button primary"
                      type="button"
                      disabled={Boolean(busy) || !dirty}
                      onClick={() =>
                        run(file.name, () =>
                          post('/api/brandkit', { name: file.name, content: drafts[file.name] })
                        )
                      }
                    >
                      {busy === file.name ? (
                        <LoaderCircle className="spin" size={15} />
                      ) : (
                        <Save size={15} />
                      )}
                      Salvar
                    </button>
                    <button
                      className="button"
                      type="button"
                      disabled={Boolean(busy) || !dirty}
                      onClick={() => setDrafts({ ...drafts, [file.name]: file.content })}
                    >
                      <RotateCcw size={14} /> Desfazer
                    </button>
                  </div>
                </div>
              ) : null}
            </section>
          );
        })}
      </div>

      <p className="muted kit-note">
        Campo vazio some do prompt em vez de virar lacuna: o agente não inventa o que você não
        escreveu. Preço, endereço e condição continuam vindo só dos fatos confirmados no briefing.
      </p>
    </>
  );
}
