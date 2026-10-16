import React, { useEffect } from 'react';
import {
  ArrowDown,
  ArrowUpRight,
  Images,
  LineChart,
  MessagesSquare,
  PenLine,
  ShieldCheck,
  Sparkles,
  Store,
} from '../../shared/icons.js';
import PublicHeader from '../../shared/components/PublicHeader.jsx';
import WhatsAppButton from '../../shared/components/WhatsAppButton.jsx';
import RotatingText from '../../shared/components/RotatingText.jsx';
import HeroScene3D from './HeroScene3D.jsx';
import {
  FEATURED_STORE_CATEGORIES,
  STORE_CATEGORIES,
} from '../../shared/catalog/storeCategories.js';
import useHomeMotion from './useHomeMotion.js';
import arte1 from '../../assets/showcase/arte-1.webp';
import arte2 from '../../assets/showcase/arte-2.webp';
import arte3 from '../../assets/showcase/arte-3.webp';
import arte4 from '../../assets/showcase/arte-4.webp';
import logoRealCenter from '../../assets/clientes/real-center.webp';

// Public landing page. It talks about the product, never about a particular store, so
// nothing here reads from the session.

// Real output, not mockups: these came out of the product.
const SHOWCASE = [
  {
    src: arte1,
    width: 1122,
    height: 1402,
    alt: 'Arte de lançamento de suco com preço em destaque',
    tag: 'Produto',
  },
  {
    src: arte3,
    width: 560,
    height: 700,
    alt: 'Arte de promoção de chaleira elétrica com desconto',
    tag: 'Promoção',
  },
  {
    src: arte4,
    width: 560,
    height: 700,
    alt: 'Arte de anúncio de vaga de emprego',
    tag: 'Institucional',
  },
  {
    src: arte2,
    width: 1254,
    height: 1254,
    alt: 'Arte de promoção de Suco Garoto 2L',
    tag: 'Destaque',
  },
];

const CLIENTS = [
  {
    name: 'Real Center',
    logo: logoRealCenter,
    segment: 'Supermercado · Paranavaí - PR',
    since: 'Cliente desde 2026',
    note: 'Campanhas de produto, promoção e comunicados internos publicadas no perfil da rede.',
    work: [
      { ...SHOWCASE[0], alt: 'Campanha de lançamento do suco Prats PRO+', tag: 'Lançamento' },
      { ...SHOWCASE[1], alt: 'Campanha de promoção de chaleira elétrica' },
      { ...SHOWCASE[2], alt: 'Comunicado de vaga de zeladora' },
      { ...SHOWCASE[3], alt: 'Promoção de Suco Garoto 2L' },
    ],
  },
];

const STEPS = [
  {
    icon: MessagesSquare,
    title: 'Você descreve a ideia',
    body: 'Escreva o que quer anunciar e o que está confirmado: produto, preço, data. O assistente pergunta o que faltou.',
  },
  {
    icon: PenLine,
    title: 'A equipe de agentes trabalha',
    body: 'Estratégia, calendário, headline, legenda e direção de arte. Cada etapa só começa depois que a anterior foi validada.',
  },
  {
    icon: Images,
    title: 'Você recebe o rascunho',
    body: 'Feed, Stories, carrossel ou capa de Reels com a legenda pronta. Nada é publicado sem a sua revisão.',
  },
];

const GUARANTEES = [
  {
    icon: ShieldCheck,
    title: 'Não inventa informação',
    body: 'Preço, validade e endereço só entram quando você confirma. Na dúvida, o campo fica de fora e a pendência é registrada.',
  },
  {
    icon: Store,
    title: 'Cada loja é separada',
    body: 'Sua marca, suas campanhas e seu histórico ficam isolados. Nenhuma outra loja enxerga o seu material.',
  },
  {
    icon: LineChart,
    title: 'Consumo transparente',
    body: 'Você acompanha quantas campanhas e artes já usou no mês, sem surpresa no fim do período.',
  },
  {
    icon: Sparkles,
    title: 'Regras do seu ramo',
    body: 'Farmácia não promete resultado, serviço não promete prazo. As guardas mudam conforme o que você vende.',
  },
];

function Section({ className = '', children, ...props }) {
  return (
    <section className={`home-section ${className}`} {...props}>
      {children}
    </section>
  );
}

export default function Home({ signedIn = false }) {
  const scope = useHomeMotion();
  useEffect(() => {
    const section = window.location.hash.slice(1);
    if (!['clientes', 'como-funciona'].includes(section)) return;
    const frame = requestAnimationFrame(() => {
      document.getElementById(section)?.scrollIntoView({
        behavior: 'instant',
        block: 'start',
      });
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  return (
    <>
      <PublicHeader signedIn={signedIn} />
      <main id="main-content" ref={scope} className="home w-full overflow-x-clip">
        <div className="mx-auto w-full max-w-(--home-max-width) px-(--home-gutter)">
          <section className="home-hero" aria-label="Studio AI para o comércio local">
            <HeroScene3D />
            <h1 className="max-w-6xl text-balance">
              Campanhas para
              <RotatingText words={STORE_CATEGORIES} />
            </h1>
            <div className="mt-8 flex max-w-2xl flex-col items-start gap-6">
              <p className="home-lead max-w-2xl">
                Uma equipe de agentes de marketing que entende o seu ramo, respeita o seu Brand Kit
                e entrega arte e legenda prontas para revisar. Você aprova, você publica.
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <a className="button primary min-h-12" href={signedIn ? '/studio' : '/login'}>
                  {signedIn ? 'Abrir Studio' : 'Entrar no Studio'}{' '}
                  <ArrowUpRight size={18} aria-hidden="true" />
                </a>
                <a className="button min-h-12" href="#como-funciona">
                  Como funciona <ArrowDown size={16} aria-hidden="true" />
                </a>
              </div>
            </div>
            <div
              className="home-showcase mt-14 grid grid-flow-dense grid-cols-2 gap-3 md:grid-cols-4 md:gap-5"
              aria-label="Artes criadas pelo Studio"
              data-reveal-row
            >
              {SHOWCASE.map((item) => (
                <figure className="home-art group" key={item.tag}>
                  <div className="aspect-4/5 overflow-hidden rounded-lg border border-line bg-surface">
                    <img
                      className="h-full w-full object-contain transition-transform duration-700 ease-out motion-safe:group-hover:scale-105"
                      src={item.src}
                      width={item.width}
                      height={item.height}
                      alt={item.alt}
                      decoding="async"
                    />
                  </div>
                  <figcaption>{item.tag}</figcaption>
                </figure>
              ))}
            </div>
            <dl
              className="home-facts mt-12 grid grid-cols-1 border-y border-line sm:grid-cols-3"
              data-reveal-row
            >
              <div>
                <dt>Agentes por campanha</dt>
                <dd className="home-fact-value">4</dd>
                <dd className="home-fact-note">Estratégia, texto, direção de arte e revisão.</dd>
              </div>
              <div>
                <dt>Categorias de negócios</dt>
                <dd className="home-fact-value">{STORE_CATEGORIES.length}</dd>
                <dd className="home-fact-note">Regras e linguagem adaptadas a cada segmento.</dd>
              </div>
              <div>
                <dt>Formatos de publicação</dt>
                <dd className="home-fact-value">6</dd>
                <dd className="home-fact-note">Peças preparadas para os principais canais.</dd>
              </div>
            </dl>
          </section>

          <Section id="clientes" aria-labelledby="clients-heading">
            <div className="mb-10 flex flex-col justify-between gap-5 md:flex-row md:items-end">
              <h2 id="clients-heading" className="max-w-xl">
                Quem já publica
                <br />
                com o Studio
              </h2>
              <p className="home-lead max-w-sm">
                Peças reais, aprovadas pela loja e publicadas no perfil dela.
              </p>
            </div>
            {CLIENTS.map((client) => (
              <article className="client-card" key={client.name}>
                <header className="flex flex-wrap items-center gap-5 border-b border-line pb-7">
                  <div className="client-logo">
                    <img
                      src={client.logo}
                      width={320}
                      height={426}
                      alt={`Logo ${client.name}`}
                      loading="lazy"
                      decoding="async"
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h3 className="text-2xl font-semibold">{client.name}</h3>
                    <p className="mt-1 text-sm text-muted">{client.segment}</p>
                  </div>
                  <p className="text-sm text-muted">{client.since}</p>
                </header>
                <p className="my-7 max-w-2xl text-muted">{client.note}</p>
                <ul
                  className="grid grid-flow-dense grid-cols-2 gap-3 md:grid-cols-4 md:gap-5"
                  data-reveal-row
                >
                  {client.work.map((piece) => (
                    <li key={piece.alt}>
                      <figure className="home-art group">
                        <div className="aspect-4/5 overflow-hidden rounded-lg border border-line bg-surface">
                          <img
                            className="h-full w-full object-contain transition-transform duration-700 ease-out motion-safe:group-hover:scale-105"
                            src={piece.src}
                            width={piece.width}
                            height={piece.height}
                            alt={piece.alt}
                            loading="lazy"
                            decoding="async"
                          />
                        </div>
                        <figcaption>{piece.tag}</figcaption>
                      </figure>
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </Section>

          <Section id="como-funciona" aria-labelledby="process-heading" className="home-process">
            <div className="home-section-header">
              <h2 id="process-heading">
                Da ideia
                <br />
                ao rascunho.
              </h2>
              <p className="home-lead mt-5 max-w-sm">
                Três passos. O trabalho pesado fica com os agentes.
              </p>
            </div>
            <div className="home-steps mt-12 grid gap-4 md:grid-cols-3" data-reveal-row>
              {STEPS.map(({ icon: Icon, title, body }, index) => (
                <article
                  className="home-step rounded-lg border border-line bg-surface p-7 md:p-8"
                  key={title}
                >
                  <div className="mb-12 flex items-center justify-between text-muted">
                    <span className="text-sm">Passo {index + 1}</span>
                    <Icon size={24} aria-hidden="true" />
                  </div>
                  <h3 className="mb-4 text-xl font-medium">{title}</h3>
                  <p className="max-w-lg leading-relaxed text-muted">{body}</p>
                </article>
              ))}
            </div>
          </Section>

          <Section aria-labelledby="segments-heading" className="home-segments">
            <div className="home-section-header">
              <h2 id="segments-heading">
                Feito para
                <br />o seu segmento.
              </h2>
              <p className="home-lead max-w-2xl">
                As regras mudam conforme o ramo. Uma farmácia não pode prometer resultado, uma
                academia não vende por quilo e uma loja de roupa não tem encarte. Aplicamos as
                regras certas para cada tipo de loja.
              </p>
            </div>
            <ul
              className="home-categories mt-12 grid grid-cols-2 content-start gap-x-6 md:grid-cols-4 md:gap-x-8"
              data-reveal-row
            >
              {FEATURED_STORE_CATEGORIES.map((segment) => (
                <li key={segment}>{segment}</li>
              ))}
              <li className="col-span-2 text-muted md:col-span-4">E muitos outros segmentos.</li>
            </ul>
          </Section>

          <Section aria-labelledby="guarantees-heading">
            <h2 id="guarantees-heading" className="mb-10" data-reveal-heading>
              O que você pode contar
            </h2>
            <div
              className="grid grid-flow-dense grid-cols-1 gap-x-8 md:grid-cols-2 lg:grid-cols-4"
              data-reveal-row
            >
              {GUARANTEES.map(({ icon: Icon, title, body }) => (
                <article className="border-t border-line py-8" key={title}>
                  <div className="mb-4 flex items-center gap-3">
                    <Icon size={22} className="shrink-0 text-muted" aria-hidden="true" />
                    <h3 className="text-lg font-medium">{title}</h3>
                  </div>
                  <p className="max-w-xl leading-relaxed text-muted">{body}</p>
                </article>
              ))}
            </div>
          </Section>

          <Section
            className="home-contact border-t border-line pt-14"
            aria-labelledby="contact-heading"
          >
            <div className="flex flex-col items-start justify-between gap-8 md:flex-row md:items-end">
              <h2 id="contact-heading" className="max-w-2xl">
                Vamos criar a próxima
                <br />
                campanha da sua loja?
              </h2>
              <WhatsAppButton>Entre em contato</WhatsAppButton>
            </div>
          </Section>
          <footer className="home-footer flex flex-col items-start justify-between gap-4 border-t border-line py-8 md:flex-row md:items-center">
            <span className="home-mark">
              Studio<strong>AI</strong>
            </span>
            <p className="text-sm text-muted">
              Rascunhos para revisão humana · o Studio nunca publica sozinho
            </p>
          </footer>
        </div>
      </main>
    </>
  );
}
