import React, { useEffect } from 'react';
import {
  ArrowUpRight,
  Clock,
  Images,
  LineChart,
  MessageCircle,
  MessagesSquare,
  PenLine,
  ShieldCheck,
  Sparkles,
  Store,
  Calendar,
} from 'lucide-react';
import PublicHeader from '../../shared/components/PublicHeader.jsx';
import WhatsAppButton from '../../shared/components/WhatsAppButton.jsx';
import RotatingText from '../../shared/components/RotatingText.jsx';
import SpotlightCard from '../../shared/components/SpotlightCard.jsx';
import {
  FEATURED_STORE_CATEGORIES,
  STORE_CATEGORIES,
} from '../../shared/catalog/storeCategories.js';
import ParticleField from './ParticleField.jsx';
import { useCountUp, useReveal } from './useMotion.js';
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
    alt: 'Arte de destaque de macarrão instantâneo',
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
      { ...SHOWCASE[3], alt: 'Destaque de Cup Noodles' },
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

function Stat({ value, suffix = '', label, icon: Icon, delay }) {
  const [ref, shown] = useReveal();
  const counted = useCountUp(value, shown);
  return (
    <SpotlightCard
      as="div"
      ref={ref}
      className={shown ? 'home-stat is-shown' : 'home-stat'}
      style={{ '--delay': `${delay}ms` }}
    >
      <strong>
        {counted}
        {suffix}
      </strong>
      <span className="title-with-icon">
        <Icon size={17} aria-hidden="true" />
        {label}
      </span>
    </SpotlightCard>
  );
}

function Section({ className = '', children, ...rest }) {
  const [ref, shown] = useReveal();
  const anchored = rest.id && window.location.hash === `#${rest.id}`;
  return (
    <section
      ref={ref}
      className={`home-section reveal ${shown || anchored ? 'is-shown' : ''} ${className}`}
      {...rest}
    >
      {children}
    </section>
  );
}

export default function Home({ signedIn = false }) {
  useEffect(() => {
    const section = window.location.hash.slice(1);
    if (!['clientes', 'como-funciona'].includes(section)) return;
    const frame = requestAnimationFrame(() => {
      document.getElementById(section)?.scrollIntoView({
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
          ? 'instant'
          : 'smooth',
        block: 'start',
      });
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  return (
    <>
      <PublicHeader signedIn={signedIn} />

      <main className="home">
        <div className="home-hero">
          <ParticleField />
          <div className="home-hero-text">
            <p className="eyebrow home-fade" style={{ '--delay': '0ms' }}>
              CAMPANHAS PARA O COMÉRCIO LOCAL
            </p>
            <h1 className="home-fade" style={{ '--delay': '80ms' }}>
              Campanhas para
              <RotatingText words={STORE_CATEGORIES} />
            </h1>
            <p className="home-lead home-fade" style={{ '--delay': '170ms' }}>
              Uma equipe de agentes de marketing que entende o seu ramo, respeita o seu Brand Kit e
              entrega arte e legenda prontas para revisar. Você aprova, você publica.
            </p>
          </div>

          <div className="home-strip" aria-label="Artes criadas pelo Studio">
            {/* Duplicated once so the marquee can loop without a visible jump. */}
            <div className="home-strip-track">
              {[...SHOWCASE, ...SHOWCASE].map((item, index) => (
                <figure className="home-art" key={`${item.tag}-${index}`}>
                  <img
                    src={item.src}
                    width={item.width}
                    height={item.height}
                    alt={index < SHOWCASE.length ? item.alt : ''}
                    aria-hidden={index >= SHOWCASE.length}
                    decoding="async"
                  />
                  <figcaption>{item.tag}</figcaption>
                </figure>
              ))}
            </div>
          </div>
        </div>

        <div className="home-stats">
          <Stat value={4} label="agentes por campanha" icon={Sparkles} delay={0} />
          <Stat
            value={STORE_CATEGORIES.length}
            label="categorias de negócios"
            icon={Store}
            delay={90}
          />
          <Stat value={6} label="formatos de publicação" icon={Images} delay={180} />
          <Stat value={5} suffix=" min" label="do briefing ao rascunho" icon={Clock} delay={270} />
        </div>

        <Section id="clientes" aria-label="Clientes atendidos" className="home-clients">
          <p className="eyebrow">CLIENTES ATENDIDOS</p>
          <h2>Quem já publica com o Studio</h2>
          <p className="home-lead">Peças reais, aprovadas pela loja e publicadas no perfil dela.</p>

          {CLIENTS.map((client) => (
            <SpotlightCard className="client-card" key={client.name}>
              <header>
                <div className="client-logo">
                  <img
                    src={client.logo}
                    width={320}
                    height={426}
                    alt={`Logo ${client.name}`}
                    decoding="async"
                  />
                </div>
                <div className="client-id">
                  <h3>{client.name}</h3>
                  <p className="client-segment">{client.segment}</p>
                  <p className="client-note">{client.note}</p>
                  <span className="client-since">{client.since}</span>
                </div>
              </header>
              <ul className="client-work">
                {client.work.map((piece) => (
                  <li key={piece.alt}>
                    <figure>
                      <img
                        src={piece.src}
                        width={piece.width}
                        height={piece.height}
                        alt={piece.alt}
                        loading="lazy"
                        decoding="async"
                      />
                      <figcaption>{piece.tag}</figcaption>
                    </figure>
                  </li>
                ))}
              </ul>
            </SpotlightCard>
          ))}
        </Section>

        <Section id="como-funciona" aria-label="Como funciona">
          <h2>Como funciona</h2>
          <p className="home-lead">Três passos. O trabalho pesado fica com os agentes.</p>
          <div className="home-grid home-steps">
            {STEPS.map(({ icon: Icon, title, body }, index) => (
              <SpotlightCard
                className="home-card"
                key={title}
                style={{ '--delay': `${index * 110}ms` }}
              >
                <span className="home-step-number">{String(index + 1).padStart(2, '0')}</span>
                <h3 className="title-with-icon">
                  <Icon size={20} aria-hidden="true" />
                  {title}
                </h3>
                <p>{body}</p>
              </SpotlightCard>
            ))}
          </div>
        </Section>

        <Section aria-label="Para quem é">
          <h2>Feito para qualquer segmento</h2>
          <p className="home-lead">
            As regras mudam conforme o ramo. Uma farmácia não pode prometer resultado, uma academia
            não vende por quilo e uma loja de roupa não tem encarte. Aplicamos as regras certas para
            cada tipo de loja.
          </p>
          <ul className="home-tags">
            {FEATURED_STORE_CATEGORIES.map((segment, index) => (
              <li key={segment} style={{ '--delay': `${index * 45}ms` }}>
                <Store size={13} aria-hidden="true" /> {segment}
              </li>
            ))}
            <li className="home-tag-more">
              <Sparkles size={13} aria-hidden="true" /> Muito Mais
            </li>
          </ul>
        </Section>

        <Section aria-label="Garantias">
          <h2>O que você pode contar</h2>
          <div className="home-grid home-guarantees">
            {GUARANTEES.map(({ icon: Icon, title, body }, index) => (
              <SpotlightCard
                className="home-card"
                key={title}
                style={{ '--delay': `${index * 90}ms` }}
              >
                {/* Icon on the title's own line: stacked above it read as a stray mark
                    with nothing tying it to the text. */}
                <h3>
                  <Icon size={18} aria-hidden="true" />
                  {title}
                </h3>
                <p>{body}</p>
              </SpotlightCard>
            ))}
          </div>
        </Section>

        <div className="home-actions home-contact">
          <WhatsAppButton>Entre em contato</WhatsAppButton>
        </div>

        <footer className="home-footer">
          <span className="home-mark">
            Studio<strong>AI</strong>
          </span>
          <p>Rascunhos para revisão humana · o Studio nunca publica sozinho</p>
        </footer>
      </main>
    </>
  );
}
