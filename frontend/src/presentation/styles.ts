import {css} from 'lit';

export const styles = css`
  :host {--surface:#fff;--canvas:#f4f6f8;--text:#172b3a;--muted:#42596b;--line:#c6d1da;
    --accent:#075b97;--soft:#e9f3fb;--warning:#784307;display:block;min-height:100dvh;
    background:var(--canvas);color:var(--text);font:16px/1.6 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color-scheme:light}
  @media(prefers-color-scheme:dark) {:host {--surface:#18242f;--canvas:#101a23;--text:#edf4fa;
    --muted:#bbcbd8;--line:#506576;--accent:#8bccff;--soft:#203c51;--warning:#ffd096;color-scheme:dark}}
  * {box-sizing:border-box} main {width:min(100%,960px);margin:auto;padding:24px 20px 64px}
  header {display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap;margin-bottom:32px}
  .brand {display:flex;align-items:center;gap:12px} .logo {width:44px;height:44px;color:var(--accent)}
  .wordmark {font-size:1.5rem;font-weight:750;letter-spacing:.12em;line-height:1.2}
  .tagline {font-size:.8rem;color:var(--muted)} .language {font-size:.8rem;display:flex;align-items:center;gap:8px}
  .eyebrow {font-size:.8rem;font-weight:700;letter-spacing:.1em;color:var(--accent);text-transform:uppercase}
  h1 {font-size:clamp(1.7rem,5vw,2.5rem);line-height:1.2;letter-spacing:-.025em;margin:12px 0 16px}
  h2 {font-size:1.15rem;line-height:1.4;margin:0 0 12px} p {margin:0 0 16px;overflow-wrap:anywhere}
  .intro {color:var(--muted);max-width:70ch} .card {padding:24px;border:1px solid var(--line);border-radius:20px;background:var(--surface);margin-top:20px}
  .note {padding:16px 20px;border-inline-start:4px solid var(--accent);background:var(--soft);border-radius:8px;margin-top:16px}
  .warning {border-inline-start-color:var(--warning)} .note p:last-child {margin-bottom:0}
  .badge {display:inline-block;border:1px solid var(--line);border-radius:999px;padding:2px 10px;font-size:.75rem;font-weight:650;margin-inline-end:8px}
  form {display:grid;gap:20px} .field {display:grid;gap:6px} label {font-weight:650}
  input,select {font:inherit;color:var(--text);background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 12px;min-width:0;max-width:100%}
  select {padding:6px 10px} small,.help {font-size:.875rem;color:var(--muted)} .error {font-size:.9rem;color:var(--warning);margin:0}
  input[aria-invalid=true] {border:2px solid var(--warning)}
  .actions {display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-top:20px} form .actions {margin-top:0}
  button {font:inherit;font-weight:650;min-height:44px;padding:9px 18px;max-width:100%;border:1px solid var(--accent);border-radius:999px;background:transparent;color:var(--accent);cursor:pointer;overflow-wrap:anywhere}
  button.primary {background:var(--accent);color:var(--surface)} button:disabled {opacity:.55;cursor:wait}
  :focus-visible {outline:3px solid var(--accent);outline-offset:4px}
  dl {display:grid;grid-template-columns:minmax(0,1fr) minmax(0,2fr);gap:10px 20px;margin:0}
  dt {color:var(--muted)} dd {margin:0;overflow-wrap:anywhere} code {font-size:.85rem;overflow-wrap:anywhere;white-space:normal}
  details {margin-top:28px;color:var(--muted)} summary {cursor:pointer;min-height:44px;padding:8px 0} details ul {padding-inline-start:24px}
  .requests {list-style:none;padding:0;margin:0} .requests>li {padding:20px 0;border-top:1px solid var(--line)} .requests>li:first-child {border-top:0;padding-top:0}
  .request-title {display:flex;gap:8px;justify-content:space-between;flex-wrap:wrap;font-weight:650}
  footer {margin-top:32px} .busy {font-size:.875rem;color:var(--muted);margin-top:12px}
  @media(max-width:480px) {main {padding:20px 16px 48px}.card {padding:20px 16px;border-radius:16px} header {gap:16px} dl {grid-template-columns:1fr;gap:2px} dd {margin-bottom:12px}}
  @media(prefers-reduced-motion:reduce) {* {animation:none!important;transition:none!important;scroll-behavior:auto!important}}
`;
