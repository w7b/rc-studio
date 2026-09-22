import React, { useEffect, useRef } from 'react';
import { prefersReducedMotion } from './useMotion.js';

// A drifting constellation behind the hero.
//
// Canvas 2D on purpose: Three.js would add roughly 600 KB to a bundle that is currently
// under 300 KB, for a page whose visitors are shopkeepers often on mobile data. This is
// about two kilobytes and gives the same impression.
export default function ParticleField() {
  const canvas = useRef(null);

  useEffect(() => {
    const element = canvas.current;
    if (!element || prefersReducedMotion()) return undefined;

    const context = element.getContext('2d');
    let width = 0,
      height = 0,
      frame,
      running = true;
    const points = [];
    const ratio = Math.min(window.devicePixelRatio || 1, 2);

    function accent() {
      const value =
        getComputedStyle(document.documentElement).getPropertyValue('--brand').trim() || '#e5e5e5';
      const hex = value.replace('#', '');
      const full = hex.length === 3 ? hex.replace(/./g, (c) => c + c) : hex;
      return [0, 2, 4].map((offset) => parseInt(full.slice(offset, offset + 2), 16) || 0);
    }
    let [r, g, b] = accent();

    function resize() {
      const rect = element.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      element.width = Math.round(width * ratio);
      element.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      // Density follows area, so a phone does not run the same load as a desktop.
      const wanted = Math.min(70, Math.max(18, Math.round((width * height) / 16000)));
      points.length = 0;
      for (let index = 0; index < wanted; index += 1) {
        points.push({
          x: Math.random() * width,
          y: Math.random() * height,
          vx: (Math.random() - 0.5) * 0.22,
          vy: (Math.random() - 0.5) * 0.22,
          size: Math.random() * 1.6 + 0.7,
        });
      }
    }

    function draw() {
      if (!running) return;
      context.clearRect(0, 0, width, height);
      for (const point of points) {
        point.x += point.vx;
        point.y += point.vy;
        // Wrap rather than bounce: no visible edge to the field.
        if (point.x < -10) point.x = width + 10;
        if (point.x > width + 10) point.x = -10;
        if (point.y < -10) point.y = height + 10;
        if (point.y > height + 10) point.y = -10;
      }
      for (let i = 0; i < points.length; i += 1) {
        for (let j = i + 1; j < points.length; j += 1) {
          const dx = points[i].x - points[j].x;
          const dy = points[i].y - points[j].y;
          const distance = Math.hypot(dx, dy);
          if (distance < 130) {
            context.strokeStyle = `rgba(${r}, ${g}, ${b}, ${(1 - distance / 130) * 0.16})`;
            context.lineWidth = 1;
            context.beginPath();
            context.moveTo(points[i].x, points[i].y);
            context.lineTo(points[j].x, points[j].y);
            context.stroke();
          }
        }
      }
      for (const point of points) {
        context.fillStyle = `rgba(${r}, ${g}, ${b}, 0.5)`;
        context.beginPath();
        context.arc(point.x, point.y, point.size, 0, Math.PI * 2);
        context.fill();
      }
      frame = requestAnimationFrame(draw);
    }

    function onVisibility() {
      // A hidden tab should not keep a rAF loop alive burning battery.
      running = !document.hidden;
      if (running) frame = requestAnimationFrame(draw);
      else cancelAnimationFrame(frame);
    }

    resize();
    draw();
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      running = false;
      cancelAnimationFrame(frame);
      observer.disconnect();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, []);

  return <canvas className="particle-field" ref={canvas} aria-hidden="true" />;
}
