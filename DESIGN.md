---
version: alpha
name: Studio AI
description: Marketing para o comércio local, com navegação translúcida e administração sóbria.
colors:
  primary: '#ef863d'
  background: '#131313'
  surface: '#171717'
  text: '#e5e5e5'
  muted: '#a3a3a3'
  whatsapp: '#25d366'
typography:
  sans:
    fontFamily: 'Google Sans, Segoe UI, Arial, sans-serif'
  mono:
    fontFamily: 'ui-monospace, monospace'
rounded:
  DEFAULT: '10px'
  card: '13px'
  navigation: '16px'
spacing:
  page-max: '1080px'
  section-gap: '72px'
components:
  button: {}
  card: {}
  dialog: {}
  navigation: {}
  metrics: {}
---

# Studio AI Design System

## Overview

### Creative North Star

Uma bancada de criação para pequenos comerciantes: as artes reais ocupam a vitrine,
enquanto os controles usam superfícies discretas e uma única cor de destaque.
A assinatura pública é o nome completo de cada categoria sendo escrito e apagado.

### Product context and register

Comerciantes brasileiros usam o Studio em português para produzir e revisar campanhas.
A home e o login têm registro de apresentação; `/studio` e `/admin` são ferramentas
operacionais. O painel privilegia comparação de números, leitura e ações explícitas.
Referências: README, ADR 002 e pedido de navegação com glassmorphism. Preservar a
marca existente; evitar gradientes decorativos nos números, bordas pesadas e dados fictícios.

`shared/styles/tokens.css` é a fonte canônica de variáveis (modelo B): marca,
superfícies, texto, bordas, feedback, vidro, sombras, espaçamento e movimento.
`global.css` ordena as camadas de base, tema, responsividade, telas e efeitos.
`app/studio-shell.css` concentra a navegação; `controls.css` contém estados dos
controles compartilhados. Layout novo usa utilitários Tailwind nos componentes.
Esses estilos consomem os tokens; `applyTheme.js` adapta a marca
por loja e escolhe o texto de contraste. Este documento espelha os valores.

## Colors

Fundo neutro #131313, superfície #171717, texto #e5e5e5 e apoio #a3a3a3. Destaque #ef863d.
WhatsApp #25d366 identifica contato. Cores de loja só se aplicam ao Studio;
home e login restauram o tema público. Erro e sucesso mantêm texto explicativo.
Inputs, selects e textareas usam `--field-background: var(--surface-1)`, borda
`--line-strong` e hover `--line-hover`, com foco na marca. Autofill usa a mesma
superfície, inclusive com foco. O foco dos campos muda a borda existente de 1px,
sem empilhar outline e sombra. Botões usam `--control-background` e `--control-hover`,
derivados de `--surface-2` e `--surface-3`. Não adicionar cinzas fixos nos componentes.
Feedback usa tokens semânticos `--danger-*`, `--success-*` e `--warning-text`.
Nova tentativa de campanha fecha o menu de ações e pede confirmação em modal.
Avisos de custo usam amarelo (`--warning-*`); solicitações aceitas usam feedback
verde, sem antecipar o sucesso da geração. Falhas e exclusões mantêm vermelho.
No Studio, botões de ação têm fundo neutro e brilho localizado na cor da loja,
acompanhando o cursor como nos cards públicos. Ações de aviso e perigo preservam
suas cores semânticas. O menu lateral desliza ao abrir/fechar, inicia aberto no
desktop e permanece aberto ao navegar; o X fecha e o hambúrguer reabre.
Não há botão de fixar/desafixar. No celular, usa sobreposição.
Submenus começam recolhidos; clicar no módulo pai navega e expande os filhos.
A flecha alterna a expansão sem navegar. Todas as quinas dos itens têm o mesmo raio.
A seta usa fundo transparente, com hover apenas no ícone e contorno somente no foco por teclado.
Breadcrumbs e URLs refletem pais e filhos: Marketing → Biblioteca → Referências,
`/studio/library/references`. URLs antigas redirecionam preservando parâmetros.
Configurações reúne Dados pessoais, Segurança, Dados da loja e Brand Kit em subrotas.
Tooltips em pílula aparecem em ações só com ícones e nas dicas de campos, com foco
por teclado e Escape. Seleções de imagens e campanhas usam busca, duas linhas por
resultado e painel limitado à largura do campo/viewport. Imagens mostram miniatura
na lista e no campo selecionado; referências incluem tipo e dimensões.
Produto e referência de campanha usam linhas compactas com título e opções de origem:
biblioteca, arquivo ou nenhuma. Explicações ficam em `FieldHelp`; os campos aparecem
somente para biblioteca ou envio. Somente a origem ativa entra no pedido.
A troca de página usa uma entrada curta de opacidade e deslocamento de 6px,
sem remontar formulários por animação. Respeitar movimento reduzido.
O controle de visibilidade da senha mantém fundo transparente no hover e destaca
apenas o cadeado com `--brand-soft`, preservando a área clicável e o foco por teclado.

## Typography

Google Sans variável, hospedada localmente com licença SIL OFL, para títulos e corpo;
Segoe UI/Arial como fallback. Títulos públicos maiores e peso 650, com espaçamento
entre letras de -0.04em. Números administrativos usam algarismos tabulares; identificadores
usam monospace. Datas e números seguem pt-BR. Custos de API mostram USD explicitamente.

## Layout

Home limitada a 1080px. Menu fixo centralizado, 18px do topo, com respiro lateral de 20px.
No celular, respiro de 12px. Métricas em quatro colunas, duas abaixo de 1100px.
Página rola naturalmente; apenas tabelas e listas extensas têm rolagem interna.
Texto animado reserva altura para duas linhas, inclusive nas categorias mais longas.

## Elevation & Depth

Menu público usa rgba(187,187,187,0.31), blur de 13.3px, raio de 16px,
borda rgba(187,187,187,0.42), brilho interno branco a 10% e sombra 0 4px 30px com preto a 10%.
Links à esquerda com 64px de distância da marca no desktop; Entrar à direita.
Abaixo de 420px, links na segunda linha para manter espaço e legibilidade.
Demais superfícies de vidro derivam de `--surface-1` a 50% e blur de 8px.
Botões, indicadores da home e clientes
ganham laranja no hover. Nos clientes, `SpotlightCard` limita o brilho à região do cursor,
com raio e cor definidos por `--spotlight-radius` e `--spotlight-color`; não colore nem
move o card inteiro. Desativado para toque e movimento reduzido.
O mesmo componente atende indicadores, Como funciona, garantias, WhatsApp e Entrar,
preservando links e botões nativos. Botões usam raio de 90px; o login sólido usa brilho
claro para manter contraste. Números dos passos usam `--text-muted`.
Artes da vitrine usam molduras 4:5 com `object-fit: cover`, sem distorção, com recorte
central nas imagens de proporção diferente.
Menu de ações usa portal no body, posição fixa e colisão com
os limites da janela. Modal usa a top layer do dialog nativo e margens automáticas.

## Shapes

Controles com raio de 10px, cards 13px e menu público 16px. Bordas de controles derivam
do texto a 13%; borda mais visível só no hover/foco. Não remover foco para suavizar outline.

## Components

### Foundational visual states

Hover, foco visível, pressionado e desabilitado são globais. Processamento bloqueia
envios duplicados. Carregamento e erros são anunciados. Nenhum valor fictício preenche
métricas indisponíveis; dados vazios continuam explicitamente zerados.

### Buttons and actions

`.button` é a receita compartilhada de baixo contraste; `.primary` representa a ação
principal. `WhatsAppButton` concentra o ícone e o destino de contato. Ações de risco
usam confirmação com Cancelar inicialmente focado.

### Navigation and data display

`PublicHeader` compartilha o menu entre home e login. `routes.js` é o mapa canônico do
Studio. `MetricCard`, `AdminMetrics` e `IntegrationStatus` concentram apresentação de dados.
O gráfico diário inclui tabela acessível; lojas têm busca e paginação de oito itens.
`StoreAccessPanel` reúne título, busca, Nova loja, totais, lista e paginação em uma
única superfície. A vitrine de segmentos usa 20 categorias representativas e “Muito Mais”;
o catálogo completo permanece nos formulários e na animação do título.
Cada loja tem um único menu `...`: acessos, convites, módulos, chaves de modelos e status.
Cargos e remoções ficam em `StoreMembers`; `StoreModelKeys` recebe apenas indicadores
de configuração, nunca as chaves armazenadas.

`Library` separa Imagens de Produtos do Brand Kit e Artes de campanhas, compartilhando
busca, ordenação e cards. O tipo Imagem em Referências cadastra um produto por upload.
Na campanha, arte e legenda vêm primeiro; entregas dos agentes ficam recolhidas em
Detalhes da campanha, com os nomes Textos, Planejamento, Direção da arte e Revisão.

O menu público é estilizado pela seção `.public-header` de `shared/styles/platform.css`.
Seus tokens ficam em `tokens.css`: `--public-menu-width` (1080px),
`--public-menu-radius` (16px), `--public-menu-top` (18px), `--public-menu-background`,
`--public-menu-border`, `--public-menu-blur` e `--public-menu-shadow`.

### Forms and overlays

A criação de campanha usa uma bancada com modelo no cabeçalho, briefing amplo e
configurações laterais, empilhadas em telas estreitas. Informações complementares
e guia da equipe são recolhíveis. O editor em Referências mantém original e resultado
visíveis para comparar; fundo quadriculado indica transparência, sem confundir esse
estado com uma textura gravada no arquivo.

`Modal` concentra centralização, Escape, inert nativo e restauração de foco.
`ActionMenu` concentra portal, teclado e fechamento. `CategoryField` reutiliza o
catálogo de categorias e aceita texto livre. Listas curtas usam select/datalist nativos;
campanhas e imagens usam `SearchSelect`, com busca, texto limitado e navegação por teclado.
Erros ficam junto da operação que falhou.
`Feedback` separa mensagem e ação com 12–16px; alertas têm margem vertical de 12px
e deixam ao menos 16px antes de cards adjacentes. Rótulos internos ficam a 8px dos
campos; grades de formulários usam 16px entre colunas e 20px entre linhas.
`PasswordInput` mantém a senha oculta inicialmente e usa `Lock`/`LockOpen` do Lucide para alternar visibilidade,
com nome acessível e estado pressionado. Reutilizado no login, convite, conta e integrações.
`StoreCategoriesModal` apresenta o catálogo completo com busca e até três seleções.
Cancelar descarta o rascunho do modal; Aplicar seleção atualiza o formulário; Salvar
dados da loja persiste. O catálogo canônico está em `resources/catalog/store-categories.json`.

### Iconography

Lucide, 14–20px, ao lado do título ou rótulo. Marca WhatsApp em SVG próprio. Ícones
decorativos ocultos da árvore acessível; ações só com ícone recebem nome acessível.

### Motion

Hover compartilhado usa `--motion-duration: 240ms` e
`--motion-ease: cubic-bezier(0.22, 1, 0.36, 1)`, com elevação de 2px nos botões
e 3px nos cards. Menus de ações permanecem fixos ao passar o mouse. Entradas de cards
animam opacidade para não competir com o hover. Animação de digitação escreve todas as letras,
pausa 1800ms, apaga e avança. Preferência por movimento reduzido mostra texto estático.
Links Clientes e Como funciona rolam suavemente até a seção, com espaço para o menu
fixo. Com movimento reduzido, a navegação é imediata.
Studio AI no menu rola até o topo sem recarregar a home. A seção de destino encerra
sua animação de entrada antes de calcular a rolagem. O contato via WhatsApp fica após
O que você pode contar, antes do rodapé.

### Content and data visualization

Frases diretas em português, ações nomeadas por verbos. Separar conexão Meta validada
de publicação disponível. Custos sem preço são sinalizados como cobertura parcial.

## Do's and Don'ts

- Reutilizar componentes e tokens antes de criar outra versão de menu, modal ou contato.
- Manter controles de permissão no servidor e explicar estados indisponíveis na interface.
- Não usar números de demonstração como métricas de produção.
- Não usar hover como única forma de acessar ações ou dados.

## Consultoria de marketing

A rota `/studio/meta-ads/consultations` usa o módulo `meta_ads`, com os mesmos gates de sessão e loja das campanhas. Form, Textarea, Feedback, panel e button são os componentes e estilos canônicos. A seleção de campanhas usa SearchSelect com busca e texto limitado por resultado. A tela coleta fontes com conteúdo fornecido e exibe evidências, lacunas, orçamento sujeito a aprovação e custo separado por consulta. Não adiciona CSS ou etapas ao pipeline. Formulário e resultado permanecem ao navegar entre abas durante a sessão.
