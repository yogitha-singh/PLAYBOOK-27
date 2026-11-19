// Application shell: hash router, navigation, error boundary, focus management, shared dialog.
import * as api from './api.js';
import { html, raw, esc, qs } from './util.js';
import { skeleton, errorBox, toast, openDialog, closeDialog } from './components.js';
import * as command from './pages/command.js';
import * as pressure from './pages/pressure.js';
import { batters, bowlers, openPlayer, addToShortlist } from './pages/intelligence.js';
import * as compare from './pages/compare.js';
import * as leaderboard from './pages/leaderboard.js';


import * as models from './pages/models.js';
import * as stability from './pages/stability.js';
import * as status from './pages/status.js';
import * as about from './pages/about.js';

export const PAGES = [command, pressure, batters, bowlers, compare, leaderboard, stability, status, models, about];
const byPath = Object.fromEntries(PAGES.map((p) => [p.meta.path, p]));
let navToken = 0, firstRender = true;

export function parseHash(h = location.hash) {
  const [path, query = ''] = h.replace(/^#\/?/, '').split('?');
  return { path: path || 'overview', query: Object.fromEntries(new URLSearchParams(query)) };
}
const go = (path, query) => { location.hash = `#/${path}${qs(query)}`; };

function renderNav(active) {
  document.getElementById('nav-list').innerHTML = String(html`${PAGES.map((p) => html`<li><a href="#/${p.meta.path}"${p.meta.path === active ? raw(' aria-current="page"') : ''} class="nav-link">${p.meta.nav}</a></li>`)}`);
}

async function render() {
  const { path, query } = parseHash(), page = byPath[path] || command, token = ++navToken, root = document.getElementById('view');
  renderNav(page.meta.path);
  document.title = `${page.meta.title} · PLAYBOOK 27`;
  document.getElementById('page-title').textContent = page.meta.title;
  document.getElementById('crumb').textContent = page.meta.title;
  document.body.classList.remove('nav-open');
  root.innerHTML = String(skeleton());
  const ctx = { query, navigate: (q) => go(page.meta.path, q), reload: () => render(), openPlayer: async (id, role) => { try { openDialog(String(await openPlayer(id, role)), { label: 'Scouting card' }); } catch (e) { toast(e.message, 'bad'); } } };
  try {
    const data = await page.load(ctx);
    if (token !== navToken) return;                       // a newer navigation superseded this one
    root.innerHTML = String(page.view(data, ctx));
    page.mount?.(root, data, ctx);
  } catch (e) {
    if (token !== navToken) return;
    root.innerHTML = String(errorBox(e));
    root.querySelector('[data-action=retry]')?.addEventListener('click', () => render());
  }
  if (!firstRender) { document.getElementById('main').focus({ preventScroll: false }); window.scrollTo({ top: 0 }); }   // keep the skip-link first in tab order on initial load
  firstRender = false;
}

function init() {
  // The skip link must not touch the hash (it would be parsed as a route): focus <main> directly.
  document.querySelector('.skip')?.addEventListener('click', (e) => { e.preventDefault(); document.getElementById('main').focus(); });
  document.getElementById('menu-btn').addEventListener('click', (e) => { const o = document.body.classList.toggle('nav-open'); e.currentTarget.setAttribute('aria-expanded', String(o)); });
  const d = document.getElementById('dialog');
  d.addEventListener('click', async (e) => {
    if (e.target === d || e.target.closest('.dialog-close')) return closeDialog();
    const add = e.target.closest('[data-add]'); if (add) await addToShortlist(add.dataset.add, add.dataset.role);
    if (e.target.closest('a[href^="#/"]')) closeDialog();
  });
  let wasNarrow = (window.innerWidth || 1200) < 640;
  window.addEventListener('resize', () => { const n = window.innerWidth < 640; if (n !== wasNarrow) { wasNarrow = n; render(); } });
  window.addEventListener('hashchange', render);
  render();
}
if (typeof document !== 'undefined') init();

