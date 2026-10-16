import React from 'react';
import campaignArtworkOne from '../../assets/showcase/arte-1.webp';
import campaignArtworkTwo from '../../assets/showcase/arte-2.webp';
import campaignArtworkThree from '../../assets/showcase/arte-3.webp';
import campaignArtworkFour from '../../assets/showcase/arte-4.webp';

const CAMPAIGN_ARTWORKS = [
  campaignArtworkOne,
  campaignArtworkTwo,
  campaignArtworkThree,
  campaignArtworkFour,
];

export default function HeroScene3D() {
  return (
    <div className="hero-scene" aria-hidden="true" data-hero-scene>
      <div className="hero-scene-stage">
        <div className="hero-phone-tilt" data-phone-tilt>
          <div className="hero-phone">
            <span className="hero-phone-button hero-phone-action" />
            <span className="hero-phone-button hero-phone-volume-up" />
            <span className="hero-phone-button hero-phone-volume-down" />
            <span className="hero-phone-button hero-phone-side" />
            <span className="hero-phone-camera-control" />
            <div className="hero-phone-screen">
              <span className="hero-dynamic-island">
                <span className="hero-dynamic-island-lens" />
              </span>
              <div className="hero-phone-status">
                <span>9:41</span>
                <span className="hero-phone-signal">● ● ●</span>
              </div>
              <div className="hero-phone-appbar">
                <span>Studio AI</span>
                <span>Prévia</span>
              </div>
              <div className="hero-phone-campaigns">
                {CAMPAIGN_ARTWORKS.map((src, index) => (
                  <img
                    key={src}
                    src={src}
                    alt=""
                    width="1080"
                    height="1350"
                    style={{ '--campaign-index': index }}
                  />
                ))}
              </div>
              <div className="hero-phone-caption">
                <strong>Campanha pronta</strong>
                <span>Feed · 1080 × 1350</span>
              </div>
              <span className="hero-phone-home" />
            </div>
          </div>
          <div className="hero-float-card hero-float-card-copy">
            <span className="hero-float-mark" />
            <div>
              <strong>Legenda revisada</strong>
              <span>Tom da marca aplicado</span>
            </div>
          </div>
          <div className="hero-float-card hero-float-card-status">
            <span className="hero-status-dot" />
            <div>
              <strong>Pronta para publicar</strong>
              <span>Arte e texto aprovados</span>
            </div>
          </div>
        </div>
        <span className="hero-orbit hero-orbit-one" />
        <span className="hero-orbit hero-orbit-two" />
      </div>
    </div>
  );
}
