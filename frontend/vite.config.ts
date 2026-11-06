import {readFileSync} from 'node:fs';
import {defineConfig} from 'vite';

const packageEntry = import.meta.resolve('@vypdev/ha-ui/tabs');
const noticeFiles = [
  'LICENSE',
  'NOTICE',
  'LICENSES/Font-Awesome-Free-7.0.0.txt',
  'LICENSES/Home-Assistant-Apache-2.0.txt',
  'LICENSES/Material-Design-Icons-7.4.47.txt',
  'LICENSES/Web-Awesome-3.14.0-ha.2-MIT.txt',
];
const notices = noticeFiles.map(path => readFileSync(new URL('../../' + path, packageEntry), 'utf8')).join('\n\n');
// Keep the npm notices in the distributed asset without adding files to the validated bundle layout.
const postBanner = '/*! @vypdev/ha-ui notices\n' + notices.replaceAll('*/', '* /') + '\n*/';

export default defineConfig({base: './', build: {outDir: '../backend/src/domus/ui', emptyOutDir: true,
  target: 'es2024', manifest: true, assetsInlineLimit: 0,
  modulePreload: {polyfill: false}, rolldownOptions: {output: {postBanner}}}});
