// API client: same-origin by default; typed errors; short GET cache; API key kept in sessionStorage only (never in code).
import { qs } from './util.js';
let BASE = '';
const cache = new Map();
export const setBase = (b) => { BASE = b; cache.clear(); };
export class ApiClientError extends Error {
  constructor(status, code, message) { super(message); this.status = status; this.code = code; }
}
const key = () => { try { return globalThis.sessionStorage?.getItem('pb27_api_key') || ''; } catch { return ''; } };
export const setKey = (k) => { try { k ? sessionStorage.setItem('pb27_api_key', k) : sessionStorage.removeItem('pb27_api_key'); } catch { /* storage unavailable */ } };
export const hasKey = () => !!key();
async function request(method, path, { params, body, auth } = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (auth && key()) headers['X-API-Key'] = key();
  let res;
  try { res = await fetch(BASE + '/api/v1' + path + qs(params), { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined }); }
  catch { throw new ApiClientError(0, 'network', 'Cannot reach the PLAYBOOK 27 API. Is the server running?'); }
  if (res.status === 204) return null;
  const ct = res.headers.get('content-type') || '';
  const data = ct.includes('json') ? await res.json() : null;
  if (!res.ok) { const e = data?.error || {}; throw new ApiClientError(res.status, e.code || 'error', e.message || `Request failed (${res.status})`); }
  return data;
}
export async function get(path, params, { ttl = 60000 } = {}) {
  const k = path + qs(params), hit = cache.get(k);
  if (hit && Date.now() - hit.t < ttl) return hit.v;
  const v = await request('GET', path, { params }); cache.set(k, { t: Date.now(), v }); return v;
}
export const invalidate = (prefix = '') => { for (const k of [...cache.keys()]) if (k.startsWith(prefix)) cache.delete(k); };
export const write = (method, path, body, params) => { invalidate('/scouting'); return request(method, path, { body, params, auth: true }); };
export const url = (path, params) => '/api/v1' + path + qs(params);
