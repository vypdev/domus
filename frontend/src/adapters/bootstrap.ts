import {check, endpoint, fields, wireJSON} from './http-values';
import type {EntryEndpoint} from './http-values';

export interface PageBootstrap {readonly target: EntryEndpoint; readonly styleNonce: string;}

/** Nonpersonal server-rendered facts must agree with this document's actual supported location. */
export function bootstrap(raw: unknown, pageURL: unknown): PageBootstrap {
  check(typeof raw === 'string' && raw.length <= 4096 && new TextEncoder().encode(raw).byteLength <= 4096);
  check(typeof pageURL === 'string' && pageURL.length <= 4096);
  const item = fields(wireJSON(raw), ['version', 'deployment', 'application_base', 'style_nonce'], []);
  check(item.version === 1 && typeof item.style_nonce === 'string' && /^[A-Za-z0-9_-]{32}$/u.test(item.style_nonce));
  let url: URL;
  try {url = new URL(pageURL);} catch {check(false);}
  check(url.href === pageURL && !url.username && !url.password && !url.search);
  const target = endpoint({origin: url.origin, deployment: item.deployment as EntryEndpoint['deployment'],
    applicationBase: item.application_base as string});
  check(url.pathname === target.applicationBase || (target.deployment === 'native' && url.pathname === target.applicationBase.slice(0, -1)));
  return Object.freeze({target, styleNonce: item.style_nonce});
}
