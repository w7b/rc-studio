import React from 'react';
import { Coins, Download } from 'lucide-react';

const agentLabels = {
  'Marketing Director': 'Director',
  'Social Media Senior': 'Social Media',
  'Copywriter Senior': 'Copywriter',
  'Creative Producer': 'Creative',
};

function money(value) {
  if (value === null || value === undefined) return 'Preço indisponível';
  return `US$ ${Number(value).toFixed(6)}`;
}

export default function CostSummary({ usage, runId }) {
  if (!usage)
    return (
      <section className="panel cost-card p-6">
        <div className="cost-title">
          <Coins size={20} />
          <div>
            <h2>Custo da campanha</h2>
            <p>Esta campanha foi criada antes do controle de consumo.</p>
          </div>
        </div>
      </section>
    );
  const text = usage.text || {},
    image = usage.image || {},
    agents = Object.entries(text.by_agent || {});
  return (
    <section className="panel cost-card p-6">
      <div className="cost-heading">
        <div className="cost-title">
          <Coins size={20} />
          <div>
            <p className="eyebrow">CONSUMO DA API</p>
            <h2>{money(usage.total_cost_usd)}</h2>
          </div>
        </div>
        <a className="button small" href={`/api/runs/${runId}/files/usage.json`} download>
          <Download size={14} /> Dados
        </a>
      </div>
      <div className="cost-grid">
        <div>
          <span>Agentes</span>
          <strong>{money(text.cost_usd)}</strong>
          <small>
            {Number(text.total_tokens || 0).toLocaleString('pt-BR')} tokens · {text.requests || 0}{' '}
            respostas
          </small>
        </div>
        <div>
          <span>Arte</span>
          <strong>{money(image.cost_usd)}</strong>
          <small>{image.count || 0} imagem(ns) contabilizada(s)</small>
        </div>
        <div>
          <span>Cache</span>
          <strong>{Number(text.cached_tokens || 0).toLocaleString('pt-BR')} tokens</strong>
          <small>já descontados no cálculo</small>
        </div>
      </div>
      {!!agents.length && (
        <details className="cost-details">
          <summary>Ver consumo por agente</summary>
          {agents.map(([name, item]) => (
            <div key={name}>
              <span>{agentLabels[name] || name}</span>
              <span>{Number(item.total_tokens || 0).toLocaleString('pt-BR')} tokens</span>
              <strong>{money(item.cost_usd)}</strong>
            </div>
          ))}
        </details>
      )}
      <p className="cost-note">
        Estimativa em dólar pela tabela Standard da OpenAI. A arte inclui o custo base da saída em
        qualidade média; referências e texto enviados ao modelo de imagem podem acrescentar consumo.
      </p>
    </section>
  );
}
