# Evidências da revisão do frontend — 22/09/2026

## Escopo e direção

Revisão de Home, login, navegação, telas operacionais, formulários, controles,
tokens, camadas de estilo e limite de responsabilidade dos serviços. Aplicadas
as skills solicitadas minimalist-ui, impeccable, gpt-taste e as diretrizes lidas
de figma-use. A ferramenta Figma não estava conectada; não foi feita uma revisão
de arquivo Figma remoto. As alterações existentes nos testes do backend foram
preservadas. Não foram executadas chamadas pagas de IA nem mudanças em lojas reais.

## Ajustes confirmados

- Largura canônica da Home de 1440px, com composição em Tailwind.
- Menu público sólido e configuração concentrada em tokens/CSS próprios.
- Entradas laterais curtas das artes; remoção de scrub, pinning, empilhamento e
  botão de pausa após feedback. Mantida a digitação dos segmentos a pedido.
- Logo dentro da caixa e formulários pessoais alinhados com título e abas.
- Fonte Outfit local, ícones Phosphor e remoção de efeitos decorativos globais.
- Rotas novas começam no topo; query na mesma página preserva posição.
- Portais dentro de dialogs, nomes acessíveis, foco e menu móvel.
- HTTP, URLs de mídia/OAuth e conversão de arquivos em services.
- Carregamento separado de Home e App, sem aviso de chunk acima de 500kB.

## Testes automatizados executados

`npm --prefix apps/frontend test`: 38 testes passaram. Cobertura de rotas,
renderização dos formulários, fontes independentes de imagens, hierarquia de
navegação, nomes acessíveis, texto rotativo e transporte dos serviços. Foram
verificados CSRF, expiração, cancelamento, respostas malformadas e limites da
arquitetura de rede.

`pytest apps/backend/tests/test_references.py`: 46 testes passaram com
`PYTHONPATH=apps/backend/src`, `-p no:cacheprovider` e um `--basetemp` novo dentro
de `.architecture-work`. A primeira tentativa encontrou acesso negado no TEMP
global do pytest; a nova pasta isolou o problema sem alterar permissões.

Esses testes de backend verificam criação/upload, catálogo, download, edição,
preservação do original, exclusão para lixeira, rollback, limites de arquivo,
ocupação e autorização. Constituem evidência automatizada do ciclo de mídia;
não representam um fluxo completo gravado pelo navegador.

Build de produção e Prettier passaram. A auditoria premium em modo strict terminou
com zero erros/avisos (`premium-audit.json`). O detector do Impeccable retornou
lista vazia nos arquivos verificados. Auditorias estáticas não substituem os
testes e a inspeção visual descritos aqui.

## Inspeção no navegador

Chrome, servidor isolado `apps/frontend/tests/preview_server.py`, dados fictícios.
Home inspecionada em desktop e 390px; telas internas em desktop e 390px.

| Rotas | Resultado |
|---|---|
| /studio, /studio/campaigns | Formulário e lista carregam sem overflow horizontal |
| /studio/library, /studio/library/references | Biblioteca e referências carregam, estados vazios presentes |
| /studio/erp, /studio/meta-ads, /studio/meta-ads/consultations | Integrações/consulta carregam sem overflow |
| /studio/settings e account, security, store, brand-kit | Cabeçalho, navegação e formulários visíveis |
| /studio/agentes, /studio/logs, /admin | Telas carregam sem overflow horizontal |

As 15 rotas internas não apresentaram erros/warnings no console na passagem em
390px. Isso cobre carregamento e geometria; não afirma execução de cada operação
administrativa ou de integrações externas.

Verificações de interação: validação do login vazio, entrada com identidade
fictícia, ciclo de foco e Escape do menu móvel. Em Dados pessoais, foi alterado
o nome da identidade fictícia, salvo, recarregado para confirmar persistência e
restaurado ao valor inicial. O feedback exibiu Dados atualizados.

No diálogo de categorias em 390px, uma busca sem correspondência exibiu Nenhuma
categoria encontrada. Escape fechou o diálogo e restaurou o foco ao gatilho
Selecionar categorias. No menu móvel, Shift+Tab retornou à última ação; o body
ficou com overflow hidden e o workspace inerte. Escape restaurou o foco ao botão
Abrir menu e removeu inert. A âncora Clientes terminou a aproximadamente 152px
do topo no celular; as artes usam object-fit contain.

Após os ajustes das imagens enviadas pelo usuário, o título e o painel de conta
ficaram na mesma coordenada horizontal (398px no viewport desktop inspecionado).
Logo: caixa 72×72, imagem com caixa 54×54 e conteúdo proporcional contido. Na
Home não há botão de pausa nem pin-spacer; os três passos têm posição static e
transform none. As artes concluídas têm opacidade 1 e transform none. A âncora
Clientes terminou a 130px do topo no desktop, sem somar duas compensações grandes.

## Limites e pendências externas

- O seletor nativo de arquivos do Chrome não entregou o evento de upload à
  automação; o upload por UI não foi concluído. O ciclo correspondente passou
  nos testes HTTP de mídia. Não foi executada geração paga de imagens.
- Preferência de movimento reduzido está tratada no código e no texto rotativo;
  o navegador disponível não ofereceu emulação dessa preferência para a inspeção.
- A limpeza foi parcial por acesso negado do Windows. Consulte
  `frontend-cleanup.json`; os diretórios recusados não foram alterados.
- A Home ganhou uma cena 3D decorativa em CSS no hero. O Figma remoto não foi
  alterado; as próximas ideias continuam em `frontend-guide.md` para decisão conjunta.
