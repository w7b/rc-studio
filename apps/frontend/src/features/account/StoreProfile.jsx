import Form from '../../shared/components/Form.jsx';
import React, { useCallback, useEffect, useState } from 'react';
import { Check, LoaderCircle, Store, Tags } from 'lucide-react';
import { api, post } from '../../shared/api/client.js';
import CategoryField from '../../shared/components/CategoryField.jsx';
import StoreCategoriesModal from './StoreCategoriesModal.jsx';

// The store's own identity. The agents read these fields when they write a caption or
// brief an image, which is why address and phone live here and not on a person's account:
// two people sharing a shop must not produce two different addresses on the art.
const CLAIM_LABELS = {
  alimento: 'Alimento e bebida',
  saude: 'Farmácia, suplemento e cosmético',
  servico: 'Serviços',
  varejo_geral: 'Varejo em geral',
};

const DELIVERABLE_LABELS = {
  stories: 'Stories',
  feed: 'Feed',
  leaflet: 'Encarte',
  banner: 'Banner',
};

export default function StoreProfile({ onSaved }) {
  const [state, setState] = useState(null),
    [form, setForm] = useState(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [done, setDone] = useState(false),
    [choosingCategories, setChoosingCategories] = useState(false);

  const load = useCallback(async () => {
    try {
      const value = await api('/api/store');
      setState(value);
      setForm({ ...value.profile, hashtags: (value.profile.hashtags || []).join(' ') });
      setError('');
    } catch (failure) {
      setError(failure.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function field(name, value) {
    setForm((current) => ({ ...current, [name]: value }));
    setDone(false);
  }

  function toggleDeliverable(name) {
    const current = form.deliverables || [];
    field(
      'deliverables',
      current.includes(name) ? current.filter((item) => item !== name) : [...current, name]
    );
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const saved = await post('/api/store', form);
      setState(saved);
      setForm({ ...saved.profile, hashtags: (saved.profile.hashtags || []).join(' ') });
      setDone(true);
      if (onSaved) await onSaved();
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  if (!form)
    return (
      <section className="panel p-6">
        {error ? (
          <p className="auth-error" role="alert">
            {error}
          </p>
        ) : (
          <p className="muted">Carregando…</p>
        )}
      </section>
    );

  const fonts = state?.options?.fonts || [];

  return (
    <Form noValidate className="panel p-6 account-panel" onSubmit={submit}>
      <header>
        <p className="eyebrow">
          <Store size={13} aria-hidden="true" /> DADOS DA LOJA
        </p>
        <h2>Identidade e contato</h2>
        <p className="panel-lead">
          É daqui que os agentes tiram nome, endereço, telefone e hashtags ao escrever a legenda e
          montar a arte. Campo vazio é simplesmente omitido — nada é inventado.
        </p>
      </header>

      {error ? (
        <p className="auth-error" role="alert">
          {error}
        </p>
      ) : null}
      {done ? (
        <p className="account-done" role="status">
          <Check size={15} /> Dados da loja atualizados.
        </p>
      ) : null}

      <div className="store-grid">
        <label className="field-label" htmlFor="store-name">
          Nome da loja
          <input
            id="store-name"
            value={form.brand_name || ''}
            required
            onChange={(event) => field('brand_name', event.target.value)}
          />
        </label>
        <CategoryField
          id="store-segment"
          value={form.segment}
          onChange={(value) => field('segment', value)}
        />
        <label className="field-label" htmlFor="store-city">
          Cidade
          <input
            id="store-city"
            value={form.city || ''}
            placeholder="Paranavaí - PR"
            onChange={(event) => field('city', event.target.value)}
          />
        </label>
        <label className="field-label store-wide" htmlFor="store-address">
          Endereço completo
          <input
            id="store-address"
            value={form.address || ''}
            placeholder="Rua Exemplo, nº 100, Centro, Paranavaí - PR"
            onChange={(event) => field('address', event.target.value)}
          />
        </label>
        <label className="field-label" htmlFor="store-phone">
          Telefone
          <input
            id="store-phone"
            type="tel"
            value={form.phone || ''}
            placeholder="(44) 3422-0000"
            onChange={(event) => field('phone', event.target.value)}
          />
        </label>
        <label className="field-label" htmlFor="store-whatsapp">
          WhatsApp
          <input
            id="store-whatsapp"
            type="tel"
            value={form.whatsapp || ''}
            placeholder="(44) 99999-0000"
            onChange={(event) => field('whatsapp', event.target.value)}
          />
        </label>
        <label className="field-label" htmlFor="store-instagram">
          Instagram
          <input
            id="store-instagram"
            value={form.instagram || ''}
            placeholder="@sualoja"
            onChange={(event) => field('instagram', event.target.value)}
          />
        </label>
        <label className="field-label store-wide" htmlFor="store-cta">
          Chamada preferida
          <input
            id="store-cta"
            value={form.cta_hint || ''}
            placeholder="convide a visitar a loja física"
            onChange={(event) => field('cta_hint', event.target.value)}
          />
        </label>
        <label className="field-label store-wide" htmlFor="store-hashtags">
          Hashtags base <small className="muted">separadas por espaço</small>
          <input
            id="store-hashtags"
            value={form.hashtags || ''}
            placeholder="#SuaLoja #Paranavai"
            onChange={(event) => field('hashtags', event.target.value)}
          />
        </label>
      </div>

      <h3 className="store-section">Identidade visual</h3>
      <div className="store-grid">
        <label className="field-label" htmlFor="store-color">
          Cor da marca
          <span className="store-color">
            <input
              id="store-color"
              type="color"
              value={form.brand_color || '#e5e5e5'}
              onChange={(event) => field('brand_color', event.target.value)}
            />
            <input
              aria-label="Cor em hexadecimal"
              value={form.brand_color || ''}
              placeholder="#E5E5E5"
              onChange={(event) => field('brand_color', event.target.value)}
            />
          </span>
        </label>
        <label className="field-label" htmlFor="store-font-primary">
          Fonte principal <small className="muted">títulos</small>
          {/* A list, not a closed select: a licensed brand font will not be on it. */}
          <input
            id="store-font-primary"
            list="font-suggestions"
            value={form.font_primary || ''}
            placeholder="herda do Brand Kit"
            onChange={(event) => field('font_primary', event.target.value)}
          />
        </label>
        <label className="field-label" htmlFor="store-font-secondary">
          Fonte secundária <small className="muted">textos de apoio</small>
          <input
            id="store-font-secondary"
            list="font-suggestions"
            value={form.font_secondary || ''}
            placeholder="herda do Brand Kit"
            onChange={(event) => field('font_secondary', event.target.value)}
          />
        </label>
        <datalist id="font-suggestions">
          {fonts.map((font) => (
            <option key={font} value={font} />
          ))}
        </datalist>
        <label className="field-label" htmlFor="store-logo">
          Caminho do logo
          <input
            id="store-logo"
            value={form.logo || ''}
            placeholder="brand/logo/logo.png"
            onChange={(event) => field('logo', event.target.value)}
          />
        </label>
      </div>

      <h3 className="store-section">Regras do ramo</h3>
      <div className="store-grid">
        <div className="store-wide store-category-summary">
          <p className="muted">
            {form.categories?.length
              ? form.categories.join(' · ')
              : `Regras atuais: ${CLAIM_LABELS[form.claim_pack] || 'Varejo em geral'}`}
          </p>
          <button className="button" type="button" onClick={() => setChoosingCategories(true)}>
            <Tags size={16} /> Selecionar categorias
          </button>
        </div>
        <fieldset className="field-label store-wide store-deliverables">
          <legend>Entregáveis</legend>
          <p className="muted">
            O que cada campanha precisa produzir. Encarte só faz sentido para quem publica um.
          </p>
          <div className="store-checks">
            {(state?.options?.deliverables || []).map((item) => (
              <label key={item} className="logs-toggle">
                <input
                  type="checkbox"
                  checked={(form.deliverables || []).includes(item)}
                  onChange={() => toggleDeliverable(item)}
                />
                {DELIVERABLE_LABELS[item] || item}
              </label>
            ))}
          </div>
        </fieldset>
      </div>

      {choosingCategories && (
        <StoreCategoriesModal
          value={form.categories || []}
          onClose={() => setChoosingCategories(false)}
          onApply={(categories) => {
            field('categories', categories);
            setChoosingCategories(false);
          }}
        />
      )}

      <button className="button primary" type="submit" disabled={busy}>
        {busy ? <LoaderCircle className="spin" size={16} /> : null}
        Salvar dados da loja
      </button>
    </Form>
  );
}
