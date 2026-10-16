# Onde alterar o frontend

Base dos caminhos: `apps/frontend/src`.

## Largura da Home

A Home tinha limites e regras espalhados entre `screens.css`, `platform.css` e a
folha da própria página. Esses estilos antigos foram removidos. Agora ajuste em
`shared/styles/tokens.css`:

```css
--home-max-width: 1440px;
--home-gutter: clamp(20px, 4vw, 64px);
--home-section-space: clamp(80px, 9vw, 144px);
```

O primeiro valor controla a largura máxima externa, incluindo as margens internas.
Para ocupar mais uma tela grande, experimente 1600px; para ocupar toda a largura,
use 100%. O gutter preserva espaço nas bordas. O contêiner está em
`features/home/Home.jsx`, com `mx-auto w-full max-w-(--home-max-width)`.
O título tem um limite separado `max-w-6xl` para manter a leitura.

## Menu público

- Conteúdo e links: `shared/components/PublicHeader.jsx`.
- Posicionamento, linha no hover e versão móvel: `shared/styles/public-header.css`.
- Cor, largura, borda, raio e distância do topo: tokens `--public-menu-*` em
  `shared/styles/tokens.css`.

Foi aplicada uma superfície sólida fosca, sem blur, com borda discreta e sublinhado
ao interagir com os links. Para uma versão mais reta, mude o raio de 8px para 0;
para maior contraste, use `var(--surface-2)` como fundo. Outra direção possível é
uma barra integrada à página, com somente borda inferior; isso também exigiria
ajustar position/top/width em `public-header.css` e o espaço superior da Home.

## Animações

`features/home/useHomeMotion.js` controla as entradas laterais das artes, passos,
segmentos e garantias:

- Distância: 48px no desktop e 18px no celular.
- Duração: `duration: 0.7`.
- Intervalo entre peças: `stagger: 0.08`.
- Início: `start: 'top 92%'`, quando o grid entra na tela.
- `once: true`: ao voltar a rolagem, as imagens permanecem no lugar.

Cada grid é um gatilho estável e seus filhos recebem a transformação alternada
entre esquerda e direita. Não há scrub,
pinning, empilhamento dos passos nem botão de pausa. A preferência do sistema por
movimento reduzido continua respeitada. As artes permanecem visíveis sem GSAP.

A digitação dos segmentos foi mantida conforme sua escolha. Está em
`shared/components/RotatingText.jsx`: 1800ms com a palavra completa, 78ms por letra
digitada e 32ms por letra apagada. O catálogo vem de
`resources/catalog/store-categories.json`. O componente suspende timers fora da
tela ou em abas ocultas. A geometria do título fica em `home-effects.css`.

## Tailwind de fato

O plugin já existia, mas folhas CSS sem camada ganhavam prioridade sobre as
utilities. `shared/styles/global.css` agora concentra as importações na camada
`components` e expõe os tokens com `@theme inline`.

O layout da Home está no JSX: `grid-cols-2 md:grid-cols-4`, `gap-3 md:gap-5`,
`lg:grid-cols-2`, `max-w-2xl`, `text-muted`, `border-line`, `bg-surface` e margens
responsivas. Novos layouts devem seguir esse padrão. CSS continua apropriado
para tokens, estados complexos e componentes compartilhados; não foi feita uma
reescrita mecânica de todo o CSS operacional.

## Requisições na service

`services/http.js` centraliza transporte, JSON, sessão, CSRF, cancelamento e erros.
Os módulos de domínio agrupam conta, sessão, campanhas, consultas, referências,
biblioteca, integrações, Brand Kit, administração e sistema. `services/files.js`
cuida da conversão de arquivos. Endpoints, métodos HTTP e builders de URLs de
download/OAuth ficam nessa pasta.

Exemplo dentro de um componente:

```js
import { accountService } from '../../services/account.js';

await accountService.updateDetails({ name, email, phone });
```

Não monte `/api/...` nem chame `fetch` nas páginas. Os componentes mantêm estado
visual, validação e ciclo de polling. `tests/service-boundary.test.js` impede a
reintrodução de acesso à rede fora de services. Mais detalhes em `services/README.md`.

## Configurações e logo

O alinhamento dos formulários pessoais e de segurança está em `.account-panel`,
em `shared/styles/screens.css`: largura 100%, máximo 680px e margem zero. Isso
mantém o painel alinhado com título e abas, sem o deslocamento por `margin: auto`.

O logo da seção Clientes está em `.client-logo` em `home-effects.css`. A célula
usa `minmax(0, 1fr)`, imagem com altura/largura de 100% e `object-fit: contain`.
A caixa de 72px mantém 8px de margem interna e preserva a proporção do logo.

## Ideias para escolhermos em 3D

| Ideia | Onde | Como começar |
|---|---|---|
| Peças de campanha em camadas | Fundo do hero da Home | Substituída pelo celular para tornar a função do objeto imediatamente reconhecível. |
| Prévia em celular | Fundo do hero da Home | **Implementado.** Aparelho com campanha real, cartões em profundidade, entrada lateral, deriva lenta e inclinação limitada pelo ponteiro. |
| Produto em pedestal | Demonstração de campanha | Um único modelo 3D de embalagem girável; exige modelo autorizado e versão estática para celular/movimento reduzido. |

A prévia em celular foi implementada como uma cena decorativa leve em
`src/features/home/HeroScene3D.jsx`. Ela reaproveita uma campanha real e não usa
canvas, WebGL ou nova dependência. Em telas menores que 1024px a cena sai do
layout, e com movimento reduzido ela permanece estática.

## Limpeza

Cinco diretórios foram enviados à Lixeira: caches pytest da raiz e do backend,
`graphify-out` desatualizado, a antiga pasta `shared/api` e fontes Google Sans
substituídas por Outfit local. ParticleField, useMotion e SpotlightCard sem uso
também saíram do código.

O Windows negou acesso a descendentes de `realcenter-marketing-ai`,
`.architecture-work/durable-pytest-cache`, `apps/backend/.architecture-work`,
`.test-work` e `apps/backend/.test-work`; esses caminhos foram preservados.
Não houve alteração de ACLs. O inventário exato está em `frontend-cleanup.json`.
Dados, backups, ambiente Python, dependências e scripts ativos foram preservados.

## Referências técnicas

- [Camadas e estilos no Tailwind](https://tailwindcss.com/docs/adding-custom-styles)
- [Tokens de tema no Tailwind](https://tailwindcss.com/docs/theme)
- [ScrollTrigger](https://gsap.com/docs/v3/Plugins/ScrollTrigger/)
- [Contextos responsivos do GSAP](https://gsap.com/docs/v3/GSAP/gsap.matchMedia%28%29/)
