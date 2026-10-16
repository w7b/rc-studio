import Form from '../../shared/components/Form.jsx';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Check,
  Copy,
  RotateCcw,
  ShieldOff,
  UsersRound,
  UserPlus,
  SlidersHorizontal,
  KeyRound,
} from '../../shared/icons.js';
import { adminService } from '../../services/admin.js';
import ActionMenu from '../../shared/components/ActionMenu.jsx';
import Modal from '../../shared/components/Modal.jsx';
import CategoryField from '../../shared/components/CategoryField.jsx';
import AdminMetrics from './AdminMetrics.jsx';
import StoreModules from './StoreModules.jsx';
import StoreAccessPanel from './StoreAccessPanel.jsx';
import InviteStoreModal from './InviteStoreModal.jsx';
import StoreMembers, { ROLE_HELP } from './StoreMembers.jsx';
import StoreModelKeys from './StoreModelKeys.jsx';

export default function AdminPanel({ onModulesChanged }) {
  const [moduleStore, setModuleStore] = useState(null),
    [accessStore, setAccessStore] = useState(null),
    [keyStore, setKeyStore] = useState(null),
    [search, setSearch] = useState(''),
    [page, setPage] = useState(1);
  const [confirmation, setConfirmation] = useState(null),
    [notice, setNotice] = useState('');
  const [data, setData] = useState(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [creating, setCreating] = useState(false),
    [inviting, setInviting] = useState(null),
    [invite, setInvite] = useState(null),
    [copied, setCopied] = useState(false);
  const [form, setForm] = useState({
    slug: '',
    name: '',
    root_path: '',
    segment: '',
    city: '',
    address: '',
    phone: '',
    whatsapp: '',
    instagram: '',
    brand_color: '',
    claim_pack: 'varejo_geral',
  });

  const load = useCallback(async () => {
    try {
      setData(await adminService.getOverview());
      setError('');
    } catch (failure) {
      setError(failure.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function act(operation, payload, after) {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await operation(payload);
      if (after) await after(result);
      await load();
      setNotice('Alteração salva.');
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  async function createStore(event) {
    event.preventDefault();
    if (!form.name.trim() || !/^[a-z0-9][a-z0-9-]{1,39}$/.test(form.slug)) {
      setError('Informe o nome e um identificador com 2 a 40 letras minúsculas, números ou hífen.');
      document.getElementById(!form.name.trim() ? 'admin-name' : 'admin-slug')?.focus();
      return;
    }
    await act(adminService.createTenant, form, () => {
      setForm({
        slug: '',
        name: '',
        root_path: '',
        segment: '',
        city: '',
        address: '',
        phone: '',
        whatsapp: '',
        instagram: '',
        brand_color: '',
        claim_pack: 'varejo_geral',
      });
      setCreating(false);
    });
  }

  const totals = useMemo(() => {
    const tenants = data?.tenants || [];
    return {
      stores: tenants.length,
      suspended: tenants.filter((tenant) => tenant.status !== 'active').length,
      members: new Set(tenants.flatMap((tenant) => tenant.members.map((m) => m.id))).size,
    };
  }, [data]);
  const matches = (data?.tenants || []).filter((tenant) =>
    `${tenant.name} ${tenant.slug}`
      .toLocaleLowerCase('pt-BR')
      .includes(search.toLocaleLowerCase('pt-BR'))
  );
  const pages = Math.max(1, Math.ceil(matches.length / 8));
  const shownPage = Math.min(page, pages);
  const selectedAccessStore = data?.tenants.find((tenant) => tenant.id === accessStore);
  const selectedKeyStore = data?.tenants.find((tenant) => tenant.id === keyStore);
  const selectedStore = data?.tenants.find((tenant) => tenant.id === moduleStore);

  if (!data)
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
          <h1>Administração</h1>
          <p className="muted mt-3">Acompanhe a plataforma e gerencie lojas, módulos e acessos.</p>
        </div>
      </div>

      {error ? (
        <p className="auth-error" role="alert">
          {error}
        </p>
      ) : null}
      {notice && (
        <p className="account-done" role="status">
          {notice}
        </p>
      )}

      <AdminMetrics />

      <StoreAccessPanel
        search={search}
        totals={totals}
        onSearch={(value) => {
          setSearch(value);
          setPage(1);
        }}
        onCreate={() => {
          setError('');
          setCreating(true);
        }}
      >
        {creating ? (
          <Modal
            title="Nova loja"
            lead="O identificador não muda depois; o resto a loja ajusta sozinha em Minha conta."
            onClose={() => setCreating(false)}
            busy={busy}
          >
            <Form noValidate onSubmit={createStore}>
              {error && (
                <p className="auth-error" role="alert">
                  {error}
                </p>
              )}
              <div className="admin-create-fields">
                <label className="field-label" htmlFor="admin-name">
                  Nome
                  <input
                    id="admin-name"
                    value={form.name}
                    required
                    placeholder="Petshop Amigo"
                    onChange={(event) => setForm({ ...form, name: event.target.value })}
                  />
                </label>
                <label className="field-label" htmlFor="admin-slug">
                  Identificador
                  <input
                    id="admin-slug"
                    value={form.slug}
                    required
                    placeholder="petshop-amigo"
                    onChange={(event) => setForm({ ...form, slug: event.target.value })}
                  />
                </label>
                <CategoryField
                  id="admin-segment"
                  value={form.segment}
                  onChange={(segment) => setForm({ ...form, segment })}
                />
                <label className="field-label" htmlFor="admin-city">
                  Cidade
                  <input
                    id="admin-city"
                    value={form.city}
                    placeholder="Paranavaí - PR"
                    onChange={(event) => setForm({ ...form, city: event.target.value })}
                  />
                </label>
                <label className="field-label admin-wide" htmlFor="admin-address">
                  Endereço
                  <input
                    id="admin-address"
                    value={form.address}
                    placeholder="Rua Exemplo, nº 100, Centro"
                    onChange={(event) => setForm({ ...form, address: event.target.value })}
                  />
                </label>
                <label className="field-label" htmlFor="admin-phone">
                  Telefone
                  <input
                    id="admin-phone"
                    value={form.phone}
                    type="tel"
                    onChange={(event) => setForm({ ...form, phone: event.target.value })}
                  />
                </label>
                <label className="field-label" htmlFor="admin-instagram">
                  Instagram
                  <input
                    id="admin-instagram"
                    value={form.instagram}
                    placeholder="@sualoja"
                    onChange={(event) => setForm({ ...form, instagram: event.target.value })}
                  />
                </label>
                <label className="field-label admin-wide" htmlFor="admin-root">
                  Raiz de dados
                  <input
                    id="admin-root"
                    value={form.root_path}
                    placeholder="opcional · vazio cria uma nova"
                    onChange={(event) => setForm({ ...form, root_path: event.target.value })}
                  />
                </label>
                <label className="field-label" htmlFor="admin-claims">
                  Pacote de alegações
                  <select
                    id="admin-claims"
                    value={form.claim_pack}
                    onChange={(event) => setForm({ ...form, claim_pack: event.target.value })}
                  >
                    <option value="alimento">Alimento e bebida</option>
                    <option value="saude">Farmácia e cosmético</option>
                    <option value="servico">Serviços</option>
                    <option value="varejo_geral">Varejo em geral</option>
                  </select>
                </label>
                <label className="field-label" htmlFor="admin-color">
                  Cor da marca
                  <span className="store-color">
                    <input
                      id="admin-color"
                      type="color"
                      value={form.brand_color || '#e5e5e5'}
                      onChange={(event) => setForm({ ...form, brand_color: event.target.value })}
                    />
                    <input
                      aria-label="Cor em hexadecimal"
                      value={form.brand_color}
                      placeholder="#E5E5E5"
                      onChange={(event) => setForm({ ...form, brand_color: event.target.value })}
                    />
                  </span>
                </label>
              </div>
              <div className="admin-create-actions">
                <button className="button primary" type="submit" disabled={busy}>
                  Criar loja
                </button>
                <button
                  className="button"
                  type="button"
                  disabled={busy}
                  onClick={() => setCreating(false)}
                >
                  Cancelar
                </button>
              </div>
            </Form>
          </Modal>
        ) : null}

        {invite ? (
          <div className="panel p-6 admin-invite" role="status">
            <p>
              Convite para <strong>{invite.email}</strong> acessar <strong>{invite.store}</strong>.
              Copie e compartilhe o link; ele aparece uma única vez:
            </p>
            <div className="admin-invite-row">
              <code>{invite.link}</code>
              <button
                className="button"
                type="button"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(invite.link);
                    setCopied(true);
                  } catch {
                    setError('Não foi possível copiar. Selecione o link e copie manualmente.');
                  }
                }}
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
                {copied ? 'Copiado' : 'Copiar'}
              </button>
              <button
                className="button"
                type="button"
                onClick={() => {
                  setInvite(null);
                  setCopied(false);
                }}
              >
                Fechar
              </button>
            </div>
          </div>
        ) : null}

        {/* One panel, flat rows. Nesting a card per store inside a card produced three
          levels of identical borders and a great deal of empty space. */}
        <div className="admin-stores">
          {!matches.length && (
            <p className="p-6 muted">
              {search
                ? 'Nenhuma loja encontrada para esta busca.'
                : 'Nenhuma loja cadastrada. Use Nova loja para começar.'}
            </p>
          )}
          {matches.slice((shownPage - 1) * 8, shownPage * 8).map((tenant) => (
            <section className="admin-store" key={tenant.id} aria-label={tenant.name}>
              <header>
                <div className="admin-store-id">
                  <h2>{tenant.name}</h2>
                  <code>{tenant.slug}</code>
                  <span className={`admin-status admin-status-${tenant.status}`}>
                    {tenant.status === 'active' ? 'Ativa' : 'Suspensa'}
                  </span>
                </div>
                <ActionMenu label={`Ações da loja ${tenant.name}`} disabled={busy}>
                  <button
                    className="button"
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setError('');
                      setKeyStore(tenant.id);
                    }}
                  >
                    <KeyRound size={14} /> Gerenciar chaves dos modelos
                  </button>
                  <button
                    className="button"
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setError('');
                      setAccessStore(tenant.id);
                    }}
                  >
                    <UsersRound size={14} /> Gerenciar acessos
                  </button>
                  <button
                    className="button"
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setError('');
                      setModuleStore(tenant.id);
                    }}
                  >
                    <SlidersHorizontal size={14} /> Gerenciar módulos
                  </button>
                  <button
                    className="button"
                    type="button"
                    role="menuitem"
                    disabled={tenant.status !== 'active'}
                    onClick={() => {
                      setError('');
                      setInviting(tenant);
                    }}
                  >
                    <UserPlus size={14} /> Convidar pessoa
                  </button>
                  <button
                    className={tenant.status === 'active' ? 'button action-danger' : 'button'}
                    type="button"
                    role="menuitem"
                    onClick={() =>
                      setConfirmation({
                        title:
                          tenant.status === 'active'
                            ? `Suspender ${tenant.name}?`
                            : `Reativar ${tenant.name}?`,
                        lead:
                          tenant.status === 'active'
                            ? 'As pessoas desta loja perderão o acesso até ela ser reativada.'
                            : 'As pessoas vinculadas voltarão a acessar esta loja.',
                        label: tenant.status === 'active' ? 'Suspender loja' : 'Reativar loja',
                        operation: adminService.setTenantStatus,
                        payload: {
                          tenant_id: tenant.id,
                          status: tenant.status === 'active' ? 'suspended' : 'active',
                        },
                      })
                    }
                  >
                    {tenant.status === 'active' ? <ShieldOff size={14} /> : <RotateCcw size={14} />}
                    {tenant.status === 'active' ? 'Suspender loja' : 'Reativar loja'}
                  </button>
                </ActionMenu>
              </header>

              {tenant.members.length === 0 ? (
                <p className="admin-empty">Nenhuma pessoa com acesso ainda.</p>
              ) : (
                <ul className="admin-members">
                  {tenant.members.map((member) => (
                    <li key={member.id}>
                      <span className="admin-member">
                        <strong>{member.name || member.email}</strong>
                        {member.name ? <span>{member.email}</span> : null}
                      </span>
                      <span className="admin-role-summary">
                        <span className="badge">{member.role}</span>
                        <small>{ROLE_HELP[member.role]}</small>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>
        <nav className="pagination" aria-label="Páginas de lojas">
          <span>
            {matches.length} lojas · página {shownPage} de {pages}
          </span>
          <button
            className="button small"
            disabled={shownPage <= 1}
            onClick={() => setPage(shownPage - 1)}
          >
            Anterior
          </button>
          <button
            className="button small"
            disabled={shownPage >= pages}
            onClick={() => setPage(shownPage + 1)}
          >
            Próxima
          </button>
        </nav>
      </StoreAccessPanel>
      {inviting && (
        <InviteStoreModal
          tenant={inviting}
          roles={data.roles}
          busy={busy}
          error={error}
          onClose={() => setInviting(null)}
          onCreate={(email, role) =>
            act(adminService.createInvite, { tenant_id: inviting.id, email, role }, (result) => {
              setInvite({ link: result.link, store: inviting.name, email });
              setCopied(false);
              setInviting(null);
            })
          }
        />
      )}
      {selectedAccessStore && (
        <StoreMembers
          tenant={selectedAccessStore}
          roles={data.roles}
          busy={busy}
          error={error}
          onClose={() => setAccessStore(null)}
          onChange={(operation, payload, after) =>
            act(operation, payload, async () => {
              after();
              await onModulesChanged?.();
            })
          }
        />
      )}
      {selectedKeyStore && (
        <StoreModelKeys
          tenant={selectedKeyStore}
          busy={busy}
          error={error}
          onClose={() => setKeyStore(null)}
          onSave={(changes, after) =>
            act(
              adminService.saveModelKeys,
              { tenant_id: selectedKeyStore.id, changes },
              async (result) => {
                after(result);
                await onModulesChanged?.();
              }
            )
          }
        />
      )}
      {selectedStore && (
        <StoreModules
          tenant={selectedStore}
          catalog={data.modules || {}}
          busy={busy}
          error={error}
          onClose={() => setModuleStore(null)}
          onToggle={(module, enabled) =>
            act(
              adminService.setModule,
              { tenant_id: selectedStore.id, module, enabled },
              async () => {
                await onModulesChanged?.();
              }
            )
          }
          onValidate={() => act(adminService.validateMetaAds, { tenant_id: selectedStore.id })}
        />
      )}
      {confirmation && (
        <Modal
          title={confirmation.title}
          lead={confirmation.lead}
          busy={busy}
          onClose={() => setConfirmation(null)}
        >
          {error && (
            <p className="auth-error" role="alert">
              {error}
            </p>
          )}
          <div className="admin-create-actions">
            <button
              className="button"
              autoFocus
              disabled={busy}
              onClick={() => setConfirmation(null)}
            >
              Cancelar
            </button>
            <button
              className="button action-danger"
              disabled={busy}
              onClick={() =>
                act(confirmation.operation, confirmation.payload, () => {
                  setConfirmation(null);
                  onModulesChanged?.();
                })
              }
            >
              {confirmation.label}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
