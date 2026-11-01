import {defineConfig} from 'vite';

export default defineConfig({base: './', build: {outDir: '../backend/src/domus/ui', emptyOutDir: true,
  target: 'es2024', manifest: true, assetsInlineLimit: 0,
  modulePreload: {polyfill: false}}});
