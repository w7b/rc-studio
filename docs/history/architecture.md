# Decisões da fundação

## Escopo e precedência

A blueprint v2.0 é referência de produto. O pedido explícito desta implementação prevalece sobre trechos que propõem seis agentes ativos, plano de tráfego e consultas SGCloud já no primeiro MVP. São quatro agentes ativos, dois planejados e nenhuma integração operacional.

## Orquestração

O Director é um Agent do OpenAI Agents SDK e mantém a conversa. Os especialistas são Agents com outputs Pydantic expostos por `as_tool`. Para o workflow de campanha completa, a aplicação disponibiliza uma etapa por vez: Social → Copywriter → Creative. O Director define orientação e escolhe chamar a tool habilitada; não há roteador por palavras-chave nem handoff de controle.

Depois de cada tool, o output validado é preservado na memória daquela execução. Os próximos especialistas recebem as entregas anteriores e o Brand Kit no contexto. O Director encerra com DirectorReview; o workflow compõe Campaign usando as entregas efetivas, sem pedir ao modelo para recopiá-las. A composição exige as três delegações e correspondência entre quadros planejados e copies. O resultado só é persistido após essas verificações.

Uma equipe nova é construída por execução, sem memória global compartilhada. Falhas de tools propagam, não são convertidas em sucesso. O Runner possui limite de turnos e a execução inteira possui timeout. O provider configurado no Director é herdado pelos especialistas. Tracing desabilitado também é herdado.

O roteiro deste MVP sempre cria uma campanha completa. Rotas menores, revisões iterativas de um especialista e persistência de conversas são evoluções futuras. O registro de delegações informa quais especialistas concluíram; não é uma plataforma de observabilidade.

## Contratos e limites

`schemas.py` define plano social, pacote de copy, briefing criativo, revisão do Director e campanha. Modelos rejeitam campos extras e textos vazios. A aplicação verifica sequência de quadros e formatos mínimos. As restrições editoriais e de fatos são instruções, não um detector infalível: revisão humana continua necessária.

Os manifests são lidos e validados; a lista de tools realmente instalada deve corresponder à allowlist. Especialistas não recebem tools externas. O diretório raiz `agents/` contém apenas dados para não sombrear o módulo Python do SDK; código instalável está em `src/realcenter_marketing`.

Arquivos de marca e briefs são referências, não instruções executáveis. O Brand Kit começa pendente; nenhum atributo oficial é inventado. Os agentes produzem conteúdo textual e especificações de produção.

## SGCloud e expansão

`SGCloudAdapter` é um Protocol interno com get_product, get_stock e get_sales. Nenhum desses nomes é um endpoint prometido. O mock usa fixtures e retorna None para dados ausentes. Não há preço ou valor monetário nos contratos. O adapter não é conectado aos agentes do MVP.

Para ativar Performance ou Analyst: definir outputs tipados, implementar capacidades necessárias, revisar allowlist, trocar status do manifesto, registrar a tool no Director e acrescentar um workflow com testes. Nenhuma dessas capacidades é simulada como ativa hoje.

## Referências técnicas

- [Orquestração e agents-as-tools](https://developers.openai.com/api/docs/guides/agents/orchestration)
- [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

Implementação conferida também contra as assinaturas do SDK Python instalado, versão 0.22.1.
