import React from 'react';
import { ArrowUpRight, FileText, ShieldCheck, Store, UserCog } from 'lucide-react';
import { STUDIO_ROUTES } from '../../shared/navigation/routes.js';
import Account from '../account/Account.jsx';
import StoreProfile from '../account/StoreProfile.jsx';
import BrandKitConfig from './BrandKitConfig.jsx';

const sections = [
  {
    id: 'account',
    label: 'Dados pessoais',
    description: 'Nome, e-mail e telefone da sua conta.',
    Icon: UserCog,
  },
  {
    id: 'security',
    label: 'Segurança',
    description: 'Alterar a senha e proteger o acesso.',
    Icon: ShieldCheck,
  },
  {
    id: 'store',
    label: 'Dados da loja',
    description: 'Identidade, contatos e informações comerciais.',
    Icon: Store,
  },
  {
    id: 'brandkit',
    label: 'Brand Kit',
    description: 'Orientações de marca usadas nas campanhas.',
    Icon: FileText,
  },
];
export default function Settings({ page, session, onUpdated, onNavigate }) {
  const items = sections.filter(({ id }) => session || id === 'brandkit');
  const link = (event, id) => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    onNavigate(id);
  };
  return (
    <div className="space-y-6">
      <header>
        <p className="eyebrow">PREFERÊNCIAS DO STUDIO</p>
        <h1>Configurações</h1>
        <p className="muted mt-2">Gerencie sua conta e as informações da loja.</p>
      </header>
      {page === 'config' ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {items.map(({ id, label, description, Icon }) => (
            <a
              key={id}
              href={STUDIO_ROUTES[id]}
              className="panel settings-link flex items-start gap-4 p-5"
              onClick={(event) => link(event, id)}
            >
              <Icon size={22} className="shrink-0" aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <strong>{label}</strong>
                <span className="mt-2 block text-sm muted">{description}</span>
              </span>
              <ArrowUpRight size={16} aria-hidden="true" />
            </a>
          ))}
        </div>
      ) : (
        <>
          <nav aria-label="Seções de configurações" className="flex flex-wrap gap-2">
            <a
              className="button small"
              href={STUDIO_ROUTES.config}
              onClick={(event) => link(event, 'config')}
            >
              Visão geral
            </a>
            {items.map(({ id, label }) => (
              <a
                key={id}
                className="button small"
                aria-current={page === id ? 'page' : undefined}
                href={STUDIO_ROUTES[id]}
                onClick={(event) => link(event, id)}
              >
                {label}
              </a>
            ))}
          </nav>
          {(page === 'account' || page === 'security') && session && (
            <Account
              key={page}
              session={session}
              onUpdated={onUpdated}
              section={page === 'security' ? 'security' : 'profile'}
            />
          )}
          {page === 'store' && session && <StoreProfile onSaved={onUpdated} />}
          {page === 'brandkit' && <BrandKitConfig />}
          {!session && page !== 'brandkit' && (
            <p className="hint">Os dados da conta ficam disponíveis no modo com login.</p>
          )}
        </>
      )}
    </div>
  );
}
