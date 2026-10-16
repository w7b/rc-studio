import { useRef } from 'react';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useGSAP } from '@gsap/react';

gsap.registerPlugin(ScrollTrigger, useGSAP);

// Fixed grid rows keep their geometry while their children replay on every viewport entry.
export default function useHomeMotion() {
  const scope = useRef(null);

  useGSAP(
    () => {
      const media = gsap.matchMedia();
      media.add(
        {
          always: '(min-width: 0px)',
          desktop: '(min-width: 768px)',
          reduced: '(prefers-reduced-motion: reduce)',
        },
        ({ conditions }) => {
          if (conditions.reduced) return;
          let disposePointer = () => {};
          const scene = scope.current.querySelector('[data-hero-scene]');
          if (scene) {
            gsap.fromTo(
              scene,
              { autoAlpha: 0, x: 48 },
              {
                autoAlpha: 0.96,
                x: 0,
                duration: 1.2,
                ease: 'power3.out',
                scrollTrigger: {
                  trigger: scene.parentElement,
                  start: 'top 95%',
                  end: 'bottom 5%',
                  toggleActions: 'restart reset restart reset',
                },
              }
            );
            gsap.to(scene.querySelector('.hero-scene-stage'), {
              y: -8,
              duration: 5.5,
              repeat: -1,
              yoyo: true,
              ease: 'sine.inOut',
            });

            const tilt = scene.querySelector('[data-phone-tilt]');
            if (tilt && window.matchMedia('(pointer: fine)').matches) {
              const rotateX = gsap.quickTo(tilt, 'rotationX', {
                duration: 0.8,
                ease: 'power3.out',
              });
              const rotateY = gsap.quickTo(tilt, 'rotationY', {
                duration: 0.8,
                ease: 'power3.out',
              });
              const onPointerMove = (event) => {
                const bounds = scene.getBoundingClientRect();
                const x = (event.clientX - bounds.left) / bounds.width - 0.5;
                const y = (event.clientY - bounds.top) / bounds.height - 0.5;
                rotateX(5 - y * 8);
                rotateY(-15 + x * 12);
              };
              const onPointerLeave = () => {
                rotateX(5);
                rotateY(-15);
              };
              const hero = scene.parentElement;
              hero.addEventListener('pointermove', onPointerMove);
              hero.addEventListener('pointerleave', onPointerLeave);
              disposePointer = () => {
                hero.removeEventListener('pointermove', onPointerMove);
                hero.removeEventListener('pointerleave', onPointerLeave);
              };
            }
          }
          scope.current.querySelectorAll('[data-reveal-row]').forEach((row) => {
            const cards = [...row.children];
            gsap.fromTo(
              cards,
              {
                x: (index) => (index % 2 === 0 ? -1 : 1) * (conditions.desktop ? 48 : 18),
                opacity: 0,
              },
              {
                x: 0,
                opacity: 1,
                duration: 0.7,
                stagger: 0.08,
                ease: 'power3.out',
                scrollTrigger: {
                  trigger: row,
                  start: 'top 92%',
                  end: 'bottom 8%',
                  toggleActions: 'restart reset restart reset',
                },
              }
            );
          });
          scope.current.querySelectorAll('[data-reveal-heading]').forEach((heading) => {
            gsap.fromTo(
              heading,
              { x: conditions.desktop ? -32 : -18, opacity: 0 },
              {
                x: 0,
                opacity: 1,
                duration: 0.65,
                ease: 'power3.out',
                scrollTrigger: {
                  trigger: heading,
                  start: 'top 92%',
                  end: 'bottom 8%',
                  toggleActions: 'restart reset restart reset',
                },
              }
            );
          });
          return disposePointer;
        }
      );
      return () => media.revert();
    },
    { scope }
  );

  return scope;
}
