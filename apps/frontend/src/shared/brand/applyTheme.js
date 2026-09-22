// Paints the store's accent onto the CSS tokens at runtime.
//
// Only the accent is per-store: the surrounding neutrals stay fixed, because letting a
// store choose its own background is how an unreadable interface gets shipped.

function clamp(value) {
  return Math.min(255, Math.max(0, Math.round(value)));
}

function parse(hex) {
  const value = String(hex || '')
    .trim()
    .replace('#', '');
  const full = value.length === 3 ? value.replace(/./g, (c) => c + c) : value;
  if (!/^[0-9a-f]{6}$/i.test(full)) return null;
  return [0, 2, 4].map((offset) => parseInt(full.slice(offset, offset + 2), 16));
}

function toHex(rgb) {
  return '#' + rgb.map((channel) => clamp(channel).toString(16).padStart(2, '0')).join('');
}

function mix(rgb, amount) {
  // Positive lightens towards white, negative darkens towards black.
  const target = amount > 0 ? 255 : 0;
  return rgb.map((channel) => channel + (target - channel) * Math.abs(amount));
}

function luminance(rgb) {
  const channels = rgb.map((channel) => {
    const ratio = channel / 255;
    return ratio <= 0.03928 ? ratio / 12.92 : Math.pow((ratio + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

const TOKENS = [
  '--brand',
  '--brand-strong',
  '--brand-soft',
  '--brand-muted',
  '--brand-ring',
  '--brand-accent',
  '--brand-contrast',
];

export function applyBrandTheme(color) {
  const root = document.documentElement;
  const rgb = parse(color);
  if (!rgb) {
    // An unset or malformed colour falls back to the stylesheet defaults.
    TOKENS.forEach((name) => root.style.removeProperty(name));
    return false;
  }
  root.style.setProperty('--brand', toHex(rgb));
  root.style.setProperty('--brand-strong', toHex(mix(rgb, -0.16)));
  root.style.setProperty('--brand-soft', toHex(mix(rgb, 0.14)));
  root.style.setProperty('--brand-muted', toHex(mix(rgb, -0.1)));
  root.style.setProperty('--brand-ring', toHex(mix(rgb, 0.22)));
  root.style.setProperty('--brand-accent', toHex(mix(rgb, -0.06)));
  // Text on the accent has to stay legible whatever the store picks.
  root.style.setProperty(
    '--brand-contrast',
    luminance(rgb) > 0.179 ? 'var(--on-light)' : 'var(--on-dark)'
  );
  return true;
}
