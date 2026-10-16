---
version: alpha
name: Studio AI
description: Marketing para o comércio local, com apresentação ampla e ferramentas foscas.
colors:
  primary: '#e5e5e5'
  background: '#131313'
  surface: '#171717'
  text: '#e5e5e5'
  muted: '#a3a3a3'
  whatsapp: '#25d366'
typography:
  sans:
    fontFamily: 'Outfit Variable, Segoe UI, sans-serif'
  mono:
    fontFamily: 'ui-monospace, monospace'
rounded:
  DEFAULT: '6px'
  card: '8px'
  navigation: '8px'
spacing:
  page-max: '1440px'
  section-gap: 'clamp(80px, 9vw, 144px)'
components:
  button: {}
  card: {}
  dialog: {}
  navigation: {}
  metrics: {}
---

# Studio AI — direção visual

## Contexto

Comerciantes brasileiros criam e revisam campanhas em pt-BR. A Home apresenta
artes reais, processo e contato. Studio e administração priorizam formulários,
estado das operações e leitura dos resultados. A direção mantém o tema escuro,
tipografia ampla, superfícies foscas, divisórias discretas e conteúdo alinhado.
Regras funcionais pertencem ao UX-CONTRACT.md.

## Fontes canônicas

Todos os caminhos abaixo estão em apps/frontend/src:

- shared/styles/tokens.css: paleta, espaçamentos, controles, largura da Home e menu público.
- shared/styles/global.css: ordem de importação, camadas e tokens Tailwind.
- shared/styles/public-header.css: geometria e estados do menu público.
- features/home/Home.jsx: composição responsiva em Tailwind.
- features/home/home-effects.css: tipografia e tratamento das imagens da Home.
- features/home/useHomeMotion.js: entrada das artes com GSAP e ScrollTrigger.
- shared/styles/controls.css: controles compartilhados.
- app/studio-shell.css: navegação do Studio.
- shared/brand/applyTheme.js: cores da loja e contraste.

Os tokens de runtime prevalecem. Este documento espelha os valores e a intenção;
não é um segundo sistema de medidas independente do código.

## Cor e material

Fundo #131313, painéis #171717, controles #202020, texto principal #e5e5e5
e secundário #a3a3a3. A marca pública é neutra clara. A marca configurada pela
loja adapta o Studio, com primeiro plano calculado para contraste; Home e login
restauram a identidade pública. Feedback usa tokens semânticos de perigo,
sucesso e aviso, sempre acompanhado de texto. Verde identifica o WhatsApp.

O menu público é opaco, com borda de 1px e raio de 8px. Não usa blur ou
glassmorphism. Superfícies operacionais usam bordas e poucos níveis de elevação;
sombras de menus/modais são leves. Reflexos que seguem o mouse e partículas
decorativas foram removidos. Gradientes não são necessários para apresentar dados.

## Tipografia e composição

Outfit Variable é hospedada no próprio build via Fontsource. O texto base herda
--font-sans; números comparáveis usam algarismos tabulares. Ícones vêm de
shared/icons.js, adaptador único do Phosphor, com peso bold no contexto global.
Ícones decorativos ficam ocultos de leitores de tela; ações têm nomes acessíveis.

A Home usa --home-max-width: 1440px, com margens internas de 20px a 64px.
Ajustar a largura nesse token, sem criar outro max-width para .home em CSS
compartilhado. Títulos escalam com o viewport; o espaço reservado à palavra
rotativa evita deslocamentos do conteúdo entre categorias longas e curtas.
As artes ocupam quatro colunas a partir de 768px e duas em telas estreitas.
Estatísticas e garantias usam linhas de separação; os passos têm cartões
em fluxo normal. O logo usa uma célula limitada, object-fit: contain e margem interna.

Home e telas internas usam rolagem do documento. Conteúdo longo não deve ser
truncado por uma altura de viewport no shell. Tabelas e seletores podem ter
rolagem própria. Formulários de conta alinham à esquerda com título e abas;
sua largura máxima de 680px mantém leitura confortável.

Novos layouts usam Tailwind. CSS mantém tokens, estados compostos e efeitos.
As folhas de componentes pertencem a layer(components), permitindo que utilitários
como grid, gap-6, max-w-2xl e text-muted prevaleçam corretamente.

## Movimento

Artes, passos, segmentos e garantias entram pelas laterais uma vez ao alcançar a
tela: deslocamento de 48px no desktop e 18px no celular, duração de 0.7s e
intervalo de 0.08s entre itens. O gatilho fica no grid estável; os filhos se
movem sem modificar o layout.
Ao terminar, transform e opacity inline são removidos. Voltar no scroll mantém
as peças no lugar. Não há scrub, pin, escala ou empilhamento dos passos.

Os nomes dos segmentos continuam sendo digitados, conforme escolha do usuário.
Não existe botão de pausa na Home. A preferência de movimento reduzido do sistema
desativa as entradas e mostra comércio local como texto estático. O texto rotativo
suspende timers fora da tela e em abas ocultas. GSAP fica restrito à Home, com
cleanup dos contextos e triggers. Conteúdo é visível sem efeitos.

## Controles e recuperação

Controles compartilhados preservam nome, foco visível, estado desabilitado e alvo
de toque de pelo menos 44px. Inputs e textareas usam o mesmo material. FieldHelp
é um botão separado do label. SearchSelect apresenta seleção, busca e estado vazio.
Tooltip, ActionMenu e SearchSelect portalam para o dialog aberto mais próximo
ou para o body, mantendo a camada nativa do modal.

Modais usam dialog.showModal(), restauração de foco, Escape e bloqueio da rolagem
de fundo. O menu móvel limita o foco e deixa o conteúdo atrás inerte. Falhas de
formulário preservam valores. Erros e estados vazios oferecem a próxima ação
quando ela existe. As regras detalhadas permanecem no contrato de interface.

## Evolução em 3D

A Home usa um celular tridimensional com uma campanha real e dois cartões de
status no fundo do hero. A cena está em `HeroScene3D.jsx` e usa perspectiva e
`translate3d` em CSS, sem WebGL ou dependência adicional. Ela aparece a partir de
1024px, responde de forma limitada ao ponteiro e permanece estática quando o
sistema pede movimento reduzido.

A próxima possibilidade — produto em pedestal — continua registrada em
`docs/frontend-guide.md` para decisão conjunta.
