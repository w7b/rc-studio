# Revisão do frontend — 22/09/2026

Objetivo: ampliar a Home, tornar o menu e a largura fáceis de configurar, aplicar
movimento às artes, corrigir inconsistências das telas e isolar HTTP em services.

## Direção e limites

Preservar fluxos, dados, pt-BR, marca por loja e alterações locais existentes.
Aplicar minimalist-ui ao acabamento fosco e à hierarquia; gpt-taste à composição
ampla e ao movimento; impeccable à acessibilidade e ao uso real das telas.
O tema escuro existente é a premissa enquanto a preferência opcional está pendente.
Itens 3D são propostas para decisão conjunta, não dependências implantadas agora.
Figma-use foi lida; não há ferramenta Figma disponível para leitura/escrita remota.

## Implementação

- [x] Home: um token de largura, Tailwind para layout, CSS da feature para efeitos.
- [x] Menu: componente compartilhado, superfície opaca, tokens e CSS próprios.
- [x] Movimento: entradas laterais com GSAP e cleanup; sem empilhamento/scrub/botão de pausa, conforme feedback. Manter segmentos sendo digitados.
- [x] Base: ordem explícita das camadas Tailwind, tokens semânticos, fonte local e ícones.
- [x] Controles: menus em modais, tooltips, foco, alvos de toque e responsividade.
- [x] Serviços: transporte central, funções por domínio, URLs fora das telas.
- [x] Limpeza: referências verificadas, cinco diretórios reciclados; cinco preservados por acesso negado do Windows, conforme inventário.
- [x] Validação: testes de serviço/rotas, mídia HTTP, build, formato e navegador; relatório em frontend-review.md.

## Verificação focada

Comparar Home, login, Studio, biblioteca, configurações e administração.
Inspecionar desktop e 390px; conferir âncoras, entradas, teclado, modal/combobox,
erros de formulário e navegação. Usar servidor de testes com dados temporários
para mutações; não gerar campanhas pagas nem alterar dados reais.
