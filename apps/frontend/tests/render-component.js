import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { transformSync } from 'esbuild';
import React from 'react';
import * as Phosphor from '@phosphor-icons/react';
import { renderToStaticMarkup } from 'react-dom/server';

const require = createRequire(import.meta.url);

// Execute the real component graph with the classic JSX transform. Keep Phosphor
// on its ESM entry: its published CommonJS path is a .js file in a module package.
export function componentModule(path) {
  const cache = new Map();
  function load(url) {
    if (url.pathname.endsWith('.css')) return {};
    if (cache.has(url.href)) return cache.get(url.href).exports;
    const module = { exports: {} };
    cache.set(url.href, module);
    const { code } = transformSync(readFileSync(url, 'utf8'), {
      loader: 'jsx',
      format: 'cjs',
      jsx: 'transform',
    });
    const resolve = (name) =>
      name === '@phosphor-icons/react'
        ? Phosphor
        : name.startsWith('.')
          ? load(new URL(name, url))
          : require(name);
    new Function('module', 'exports', 'require', code)(module, module.exports, resolve);
    return module.exports;
  }
  return load(new URL(`../src/${path}`, import.meta.url));
}

export function component(path) {
  return componentModule(path).default;
}

export function renderComponent(path, props = {}) {
  return renderToStaticMarkup(React.createElement(component(path), props));
}
