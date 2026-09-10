import React from 'react';

const modules = {
  erp: {
    title: 'ERP · SG Sistemas',
    description: 'Produtos, filiais e ofertas como base para futuras sugestões de promoção.',
    sections: [
      'Catálogo e filiais',
      'Ofertas e produtos em oferta',
      'Relatórios · Marketing Analyst',
    ],
    pending:
      'Aguardando contrato de autenticação, endereço do servidor, formatos dos dados e paginação.',
  },
  ads: {
    title: 'Meta Ads',
    description: 'Espaço preparado para conectar campanhas, criativos e resultados de mídia.',
    sections: ['Conta de anúncios', 'Campanhas e rascunhos', 'Métricas e resultados'],
    pending: 'Aguardando autenticação, conta de anúncios, permissões e versão da API.',
  },
};

// Preparation only: no fetch, effects, tokens or enabled integration actions.
export default function IntegrationModules({ type }) {
  const module = modules[type];
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">INTEGRAÇÕES</p>
          <h1>{module.title}</h1>
          <p className="muted mt-3">{module.description}</p>
        </div>
        <span className="badge">Em preparação</span>
      </div>
      <p className="hint mb-6">{module.pending} A integração está inativa.</p>
      <div className="grid md:grid-cols-3 gap-5">
        {module.sections.map((title) => (
          <section className="panel p-6" key={title}>
            <h2>{title}</h2>
            <p className="muted text-sm mt-3">Disponível após a integração ser homologada.</p>
            <button className="button mt-5" disabled>
              Em preparação
            </button>
          </section>
        ))}
      </div>
      {type === 'erp' && (
        <p className="muted mt-6">
          O analista poderá cruzar relatórios e dados do ERP, indicando a origem e a data de cada
          evidência. Margem, estoque e validade ausentes serão tratados como pendências.
        </p>
      )}
    </>
  );
}
