import React from 'react';
import { Brain, MessageCircle, PenTool, Palette, Check, LoaderCircle } from 'lucide-react';
const agents = [
  ['marketing_director', 'Marketing Director', 'Estratégia e revisão', Brain],
  ['social_media', 'Social Media', 'Calendário e conteúdo', MessageCircle],
  ['copywriter', 'Copywriter', 'Legendas e chamadas', PenTool],
  ['creative', 'Creative Producer', 'Direção visual', Palette],
];
export default function AgentTeam({ run, connected = true }) {
  const events = run?.events || [],
    current = [...events].reverse().find((e) => e.event === 'thinking')?.agent;
  return (
    <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
      {agents.map(([role, name, task, Icon]) => {
        const done = !!run?.outputs?.[role],
          working = connected && run?.status === 'running' && current?.startsWith(name) && !done;
        return (
          <div key={role} className={'agent ' + (working ? 'working' : '')}>
            <div className="flex justify-between items-center">
              <span className="agent-icon">
                <Icon size={19} />
              </span>
              {done ? (
                <Check size={16} className="text-emerald-600" />
              ) : working ? (
                <LoaderCircle size={16} className="animate-spin text-orange-600" />
              ) : (
                <span className="dot" />
              )}
            </div>
            <strong>{name}</strong>
            <p>{task}</p>
            <small>
              {done
                ? 'Entrega pronta'
                : working
                  ? 'Trabalhando…'
                  : run?.status === 'failed'
                    ? 'Pausado'
                    : 'Aguardando'}
            </small>
          </div>
        );
      })}
    </div>
  );
}
