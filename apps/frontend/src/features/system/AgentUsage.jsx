import React, { useEffect, useState } from 'react';
import { api } from '../../shared/api/client.js';

export default function AgentUsage() {
  const [data, setData] = useState(null),
    [error, setError] = useState('');
  useEffect(() => {
    let stopped = false,
      timer;
    async function refresh() {
      try {
        const value = await api('/api/usage');
        if (!stopped) {
          setData(value);
          setError('');
        }
      } catch (e) {
        if (!stopped) setError(e.message);
      }
      if (!stopped) timer = setTimeout(refresh, 5000);
    }
    refresh();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, []);
  const number = (n) => Number(n || 0).toLocaleString('pt-BR');
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">OBSERVABILIDADE</p>
          <h1>Consumo dos agentes</h1>
          <p className="muted mt-3">
            Campanhas e consultas ao Creative Producer, por agente e modelo.
          </p>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      {!data ? (
        <p>Carregando consumo…</p>
      ) : (
        <>
          <div className="grid sm:grid-cols-3 gap-5 mb-6">
            {[
              ['Entrada', data.input_tokens],
              ['Saída', data.output_tokens],
              ['Execuções registradas', data.record_count],
            ].map(([label, value]) => (
              <div key={label} className="panel p-6">
                <p className="muted">{label}</p>
                <h2 className="mt-2">{number(value)}</h2>
              </div>
            ))}
          </div>
          <div className="panel p-6 overflow-auto">
            <table className="system-table">
              <thead>
                <tr>
                  <th>Agente / modelo</th>
                  <th>Chamadas</th>
                  <th>Entrada</th>
                  <th>Saída</th>
                  <th>Entrada em cache</th>
                  <th>Gravação de cache</th>
                </tr>
              </thead>
              <tbody>
                {data.agents.map((r) => (
                  <tr key={r.agent + r.model}>
                    <td>
                      {r.agent}
                      <small className="block muted">{r.model}</small>
                    </td>
                    <td>{number(r.requests)}</td>
                    <td>{number(r.input_tokens)}</td>
                    <td>{number(r.output_tokens)}</td>
                    <td>{number(r.cached_input_tokens)}</td>
                    <td>{number(r.cache_write_input_tokens)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.agents.length && <p className="muted">Ainda não há consumo registrado.</p>}
          </div>
          <section className="panel p-6 mt-6">
            <h2>Como interpretar</h2>
            <ul className="list-disc pl-5 mt-4 space-y-2">
              {data.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
            <p className="muted text-sm mt-4">
              Os totais vêm dos registros locais disponíveis, incluindo tentativas com falha. Não
              representam a fatura da conta. Imagens aparecem no custo de cada campanha e podem ter
              tokens não informados pelo provedor.
            </p>
          </section>
        </>
      )}
    </>
  );

  return <p className="muted">Sem dados de consumo ainda.</p>;
}
