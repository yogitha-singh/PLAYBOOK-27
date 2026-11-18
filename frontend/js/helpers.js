import { spawn } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setBase } from '../js/api.js';

export const ROOT = new URL('../../', import.meta.url).pathname;
export async function startServer(port = 5077) {
  const env = { ...process.env, PLAYBOOK_ENV: 'development', PLAYBOOK_RATE_LIMIT: '100000', PLAYBOOK_DB_PATH: join(mkdtempSync(join(tmpdir(), 'pb27-')), 't.sqlite3'), PYTHONPATH: join(ROOT, 'backend') };
  delete env.PLAYBOOK_API_KEY;
  const p = spawn('python3', ['-c', `from werkzeug.serving import run_simple; from app.main import create_app; run_simple('127.0.0.1', ${port}, create_app(), threaded=True)`], { env, cwd: join(ROOT, 'backend'), stdio: 'ignore' });
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 60; i++) { try { if ((await fetch(base + '/api/v1/health')).ok) break; } catch { /* waiting */ } await new Promise((r) => setTimeout(r, 250)); }
  setBase(base);
  return { base, stop: () => p.kill() };
}
/** Minimal XML well-formedness check for chart SVG strings (balanced tags, no stray '<'). */
export function wellFormed(svg) {
  const stack = []; const re = /<\/?([a-zA-Z][\w:-]*)([^>]*?)(\/?)>/g; let m, last = 0;
  while ((m = re.exec(svg))) {
    if (svg.slice(last, m.index).includes('<')) return `stray < before index ${m.index}`; last = re.lastIndex;
    const closing = m[0].startsWith('</');
    if (m[3] === '/') continue;
    if (closing) { if (stack.pop() !== m[1]) return `unbalanced </${m[1]}>`; } else stack.push(m[1]);
  }
  return stack.length ? `unclosed <${stack.pop()}>` : (svg.slice(last).includes('<') ? 'stray <' : null);
}
export const ctx = (query = {}) => ({ query, navigate() {}, reload() {}, openPlayer() {} });
