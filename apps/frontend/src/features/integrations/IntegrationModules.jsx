import Form from '../../shared/components/Form.jsx';
import React, { useCallback, useEffect, useState } from 'react';
import { Check, Database, LoaderCircle, Megaphone } from 'lucide-react';
import { api, post } from '../../shared/api/client.js';
import IntegrationStatus from '../../shared/components/IntegrationStatus.jsx';
import PasswordInput from '../../shared/components/PasswordInput.jsx';

// Each store connects its own supplier and its own ad account, so this is configuration,
// not a fixed description of one company's vendor.
const MODULES = [
  {
    id: 'erp',
    icon: Database,
    title: 'ERP e relatórios',
    lead: 'Conecte o ERP da sua loja para puxar produtos e preços confirmados.',
    fields: [
      ['provider', 'Fornecedor', 'SG Sistemas, Bling, Tiny…'],
      ['base_url', 'Endereço da API', 'https://api.seuerp.com.br'],
      ['company_id', 'Código da empresa', ''],
      ['username', 'Usuário', ''],
    ],
    secrets: [
      ['password', 'Senha'],
      ['api_key', 'Chave de API'],
    ],
  },
  {
    id: 'meta_ads',
    icon: Megaphone,
    title: 'Meta Ads',
    lead: 'Informe a conta de anúncios usada para impulsionar as campanhas.',
    fields: [
      ['business_id', 'ID do negócio', ''],
      ['ad_account_id', 'ID da conta de anúncios', 'act_000000000'],
      ['page_id', 'ID da página', ''],
      ['api_version', 'Versão da API Meta', 'vNN.0 — versão configurada no app Meta'],
    ],
    secrets: [['access_token', 'Token de acesso']],
  },
];

function Module({ module, value, onSaved }) {
  const [form, setForm] = useState(value);
  const [secrets, setSecrets] = useState({});
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [done, setDone] = useState(false);
  const [validation, setValidation] = useState(value.validation);
  const dirty =
    module.fields.some(([name]) => (form[name] || '') !== (value[name] || '')) ||
    Boolean(form.enabled) !== Boolean(value.enabled) ||
    Object.values(secrets).some(Boolean);

  async function validate() {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      setValidation(await post('/api/integrations/meta-ads/validate', {}));
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    setDone(false);
    try {
      const payload = { ...form };
      for (const [name, secret] of Object.entries(secrets)) if (secret) payload[name] = secret;
      const updated = await post('/api/integrations', { module: module.id, values: payload });
      setSecrets({});
      setForm(updated[module.id]);
      setValidation(updated[module.id]?.validation);
      setDone(true);
      onSaved(updated);
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  const Icon = module.icon;
  return (
    <Form noValidate className="panel p-6 integration-card" onSubmit={submit}>
      <header>
        <h2>
          <Icon size={18} aria-hidden="true" /> {module.title}
        </h2>
        <label className="logs-toggle">
          <input
            type="checkbox"
            checked={Boolean(form.enabled)}
            onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
          />
          Conexão habilitada
        </label>
      </header>
      <p className="panel-lead">{module.lead}</p>

      <div className="integration-fields">
        {module.fields.map(([name, label, placeholder]) => (
          <label className="field-label" key={name} htmlFor={`${module.id}-${name}`}>
            {label}
            <input
              id={`${module.id}-${name}`}
              value={form[name] || ''}
              placeholder={placeholder}
              onChange={(event) => setForm({ ...form, [name]: event.target.value })}
            />
          </label>
        ))}
        {module.secrets.map(([name, label]) => (
          <label className="field-label" key={name} htmlFor={`${module.id}-${name}`}>
            {label}
            <PasswordInput
              id={`${module.id}-${name}`}
              visibilityLabel={label.toLocaleLowerCase('pt-BR')}
              autoComplete="new-password"
              value={secrets[name] || ''}
              /* Stored secrets are never sent back, so an empty box means "keep it". */
              placeholder={value.secrets?.[name] ? 'Guardado · preencha para substituir' : ''}
              onChange={(event) => setSecrets({ ...secrets, [name]: event.target.value })}
            />
          </label>
        ))}
      </div>

      {error ? (
        <p className="auth-error" role="alert">
          {error}
        </p>
      ) : null}
      {done ? (
        <p className="account-done" role="status">
          <Check size={15} /> Configuração salva.
        </p>
      ) : null}

      <button className="button primary" type="submit" disabled={busy}>
        {busy ? <LoaderCircle className="spin" size={16} /> : null}
        Salvar
      </button>
      <p className="muted integration-note">
        {module.id === 'meta_ads'
          ? 'Habilitar e validar a conexão não publica anúncios. A publicação pelo Studio ainda está indisponível.'
          : 'A importação do ERP ainda não está disponível. A configuração fica guardada por loja.'}
      </p>
      {module.id === 'meta_ads' && (
        <section className="module-diagnostic">
          <IntegrationStatus validation={validation} />
          <button className="button" type="button" disabled={busy || dirty} onClick={validate}>
            Validar conexão com a Meta
          </button>
          {dirty && <p className="muted">Salve as alterações antes de validar.</p>}
        </section>
      )}
    </Form>
  );
}

export default function IntegrationModules({ only = null }) {
  const [data, setData] = useState(null),
    [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setData(await api('/api/integrations'));
      setError('');
    } catch (failure) {
      setError(failure.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error)
    return (
      <p className="auth-error" role="alert">
        {error}
      </p>
    );
  if (!data) return <LoaderCircle className="spin" size={20} />;

  const shown = only ? MODULES.filter((module) => module.id === only) : MODULES;
  return (
    <div className="integration-list">
      {shown.map((module) => (
        <Module
          key={module.id}
          module={module}
          value={data[module.id] || {}}
          onSaved={(updated) => setData(updated)}
        />
      ))}
    </div>
  );
}
