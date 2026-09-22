# Consultoria e contratos de campanha

Performance Marketing e Marketing Analyst executam individualmente em
`/studio/meta-ads/consultations`, dentro de Meta Ads, por `POST /api/consultations`.
O módulo `meta_ads` governa a tela e a autorização HTTP. A campanha continua com
Director planejando, três especialistas e Director revisando: cinco chamadas normais,
sem tools. As consultas não ampliam essa sequência.

`PaidMediaPlan` organiza públicos, segmentação, testes, orçamento sugerido e medição.
`MarketingAnalysis` contém resultados, concorrentes, recomendações de SEO e lacunas.
Fontes são conteúdo fornecido pelo usuário; URLs não são acessadas pelo agente.
Cada constatação exige identificador de fonte existente e trecho literal. Sem fontes,
a análise deve declarar a ausência de dados. A interpretação continua sujeita à revisão humana.

O executor é injetado na aplicação; somente o composition root resolve o modelo.
Cada consulta reserva uma unidade de `assists`, mantém journal em `consultations/`
e participa do controle de concorrência da loja. Falhas anteriores à execução devolvem
a reserva. Não há publicação de anúncios.

O formulário serializa pedidos em `run-request.js`. A suíte Python executa o serializer
JavaScript com combinações de entradas e valida chaves/valores contra `RunRequest`.
A suíte Node verifica rotas, payloads e renderização dos componentes em JSX clássico,
incluindo regressão de `import React` ausente.

IDs de mídia antigos continuam válidos na raiz da loja. Entradas também aceitam IDs
de `/api/references`, inclusive produtos recém-salvos. Upload tem precedência sobre ID;
referências inexistentes ou de outra loja são recusadas. A origem escolhida no formulário
controla os campos enviados, sem reutilizar seleção oculta de outra origem.

Execute os checks do [guia de validação](arquitetura.md). A inspeção manual
cobre nenhuma entrada, só produto, só referência e ambos, além dos dois especialistas,
erros e mobile. Testes offline não comprovam qualidade ou disponibilidade dos provedores;
avaliações reais seguem [evals](validacao-manual.md).
