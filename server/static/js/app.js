/* AgentOS second brain — UI wiring.
 *
 * One input does everything (search / ask / commands), one map, one preview.
 * The interaction worth noticing: hovering a citation in an answer ignites the
 * node it came from, so "where does this claim live?" is answered by the map
 * rather than by reading a path.
 */
import { Orbit, RINGS } from './orbit.js';
import { md } from './md.js';

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const api = async (p, o) => {
  const r = await fetch(p, o);
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 200)}`);
  return r.json();
};

const state = { nodes: [], byId: {}, titles: new Set(), status: null, sources: [] };
const orbit = new Orbit($('#stage'));

/* ------------------------------------------------------------------ commands */

const COMMANDS = [
  { id: 'radar',    label: 'Run AI radar',        hint: 'fetch today\'s signal → brain/raw/', run: () => runJob('radar') },
  { id: 'distill',  label: 'Distil newest capture', hint: 'LLM triage → brain/output/',        run: () => runJob('distill') },
  { id: 'research', label: 'Research a topic…',   hint: 'type: > research <topic>',            run: () => toast('use  > research <topic>') },
  { id: 'sync',     label: 'Sync from git',       hint: 'git pull + reindex',                  run: doSync },
  { id: 'reindex',  label: 'Rebuild index',       hint: 'incremental, self-healing',           run: () => runJob('reindex', '/api/reindex') },
  { id: 'reset',    label: 'Reset the view',      hint: '0',                                   run: () => { orbit.reset(); toast('view reset'); } },
  { id: 'help',     label: 'Keyboard shortcuts',  hint: '?',                                   run: () => $('#help').classList.add('open') },
];

/* ---------------------------------------------------------------------- boot */

const BOOT_LINES = [
  'kernel        AGENTS.md',
  'vault         brain/ · raw → wiki → output',
  'retrieval     FTS5 + sqlite-vec · weighted RRF',
];

async function boot() {
  const bootEl = $('#boot');
  const log = $('#boot-log');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  const say = (t, cls = '') => {
    log.insertAdjacentHTML('beforeend', `<div class="${cls}">${t}</div>`);
  };
  const beat = (ms) => new Promise((r) => setTimeout(r, reduced ? 0 : ms));

  try {
    for (const l of BOOT_LINES) { say(l); await beat(90); }

    const [graph, status] = await Promise.all([
      api('/api/graph'),
      api('/api/status').catch(() => null),
    ]);

    state.nodes = graph.nodes;
    state.byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
    state.titles = new Set(graph.nodes.map((n) => n.title.toLowerCase()));
    state.status = status;

    const idx = (status && status.index) || {};
    say(`index         ${idx.meta?.mode || '?'} · ${idx.docs || 0} docs · ${idx.vectors || 0} vectors`);
    await beat(90);
    const chain = (status?.model || '').split(',');
    say(`model         ${chain[0] || 'none'}${chain.length > 1 ? ` (+${chain.length - 1} fallback)` : ''}`);
    await beat(90);
    say(`graph         ${graph.nodes.length} nodes · ${graph.edges.length} links`);
    await beat(120);
    say('ready', 'ok');
    await beat(reduced ? 0 : 380);

    orbit.setData(graph.nodes, graph.edges);
    orbit.start();
    renderLegend();
    renderStatus(graph.stats, status);

    bootEl.classList.add('gone');
    setTimeout(() => bootEl.remove(), 600);

    if (graph.missing.length) console.info('unresolved wikilinks', graph.missing);
  } catch (e) {
    say(`failed: ${e.message}`, 'err');
    say('the vault could not be loaded — check journalctl -u agentos', 'err');
  }
}

function renderLegend() {
  $('#legend').innerHTML = RINGS.slice().reverse().map((r) => `
    <button data-ring="${r.id}" style="color:${r.color}" title="show/hide ${r.label.toLowerCase()}">
      <i class="sw"></i><span>${r.label}</span><span class="n">${r.count}</span>
    </button>`).join('');
}

function renderStatus(stats, status) {
  const idx = (status && status.index) || {};
  const mode = idx.meta?.mode || 'keyword';
  const cov = Math.round((idx.coverage ?? 0) * 100);
  const vec = idx.partial
    ? `<span class="pill partial" title="reindex in progress, or one failed — run Sync to repair">${idx.vectors}/${idx.chunks} · indexing</span>`
    : `<span class="dim">${idx.vectors || 0} vec</span>`;
  const chain = (status?.model || '').split(',');

  $('#status').innerHTML = `
    <span class="ring" style="--p:${cov}" title="vector coverage ${cov}%"></span>
    <span class="pill ${mode}">${mode}</span>
    <span class="dim">${stats.docs} docs</span>
    ${vec}
    <span class="dim sep" title="${(status?.model || '').replace(/,/g, ' → ')}">${(chain[0] || 'no model').replace(/:free$/, '')}${chain.length > 1 ? ` +${chain.length - 1}` : ''}</span>`;

  const probs = (status && status.problems) || [];
  if (probs.length) {
    $('#banner').innerHTML = probs.map((p) => `<span>${p}</span>`).join(' · ');
    $('#banner').classList.add('show');
    setTimeout(() => $('#banner').classList.remove('show'), 9000);
  }
}

/* ------------------------------------------------------------- doc preview */

async function openDoc(id, { move = true } = {}) {
  const node = state.byId[id];
  if (!node) return;
  orbit.focus(id, { move });
  const p = $('#doc');
  p.classList.add('open');
  $('#doc-title').textContent = node.title;
  $('#doc-body').innerHTML = '<p class="empty">loading…</p>';
  try {
    const doc = await api('/api/doc?id=' + encodeURIComponent(id));
    const tags = (doc.tags || []).map((t) => `<span class="tag">#${t}</span>`).join('');
    const fm = Object.entries(doc.fm || {})
      .filter(([k]) => !['tags', 'title'].includes(k))
      .map(([k, v]) => `<span class="tag">${k}: ${v}</span>`).join('');
    const nb = [...orbit.neighbourhood(id)].filter((x) => x !== id);
    $('#doc-body').innerHTML = `
      <div class="meta"><span class="tag lay">${doc.layer}</span>${tags}${fm}</div>
      <div class="pathrow"><code>${doc.path}</code>
        <button data-copy="${doc.path}">copy</button></div>
      ${nb.length ? `<div class="nbr"><b>${nb.length} linked</b>${nb.map((x) =>
        `<button class="chip" data-open="${x}">${state.byId[x]?.title || x}</button>`).join('')}</div>` : ''}
      <div class="md">${md(doc.body, { exists: (n) => state.titles.has(n.toLowerCase()) })}</div>`;
    $('#doc .body').scrollTop = 0;
  } catch (e) {
    $('#doc-body').innerHTML = `<p class="empty">could not load: ${e.message}</p>`;
  }
}

function jumpToTitle(title) {
  const n = state.nodes.find((x) => x.title.toLowerCase() === title.toLowerCase());
  n ? openDoc(n.id) : toast(`no note named “${title}”`);
}

/* ------------------------------------------------------------------ palette */

let palTimer = null, palHits = [], palSel = 0, palMode = 'search';

function openPalette(seed = '') {
  $('#palette').classList.add('open');
  const inp = $('#q');
  inp.value = seed;
  inp.focus();
  inp.select();
  route(seed);
}
const closePalette = () => $('#palette').classList.remove('open');

/* One input, three modes. `>` runs a command, `?` asks the vault, anything else
   searches. Fewer surfaces to learn than three separate panels. */
function route(v) {
  const s = v.trim();
  if (s.startsWith('>')) { palMode = 'cmd'; showCommands(s.slice(1).trim()); }
  else if (s.startsWith('?')) { palMode = 'ask'; showAskPrompt(s.slice(1).trim()); }
  else { palMode = 'search'; showLocal(s); scheduleSearch(s); }
  $('#pal-mode').textContent = { search: 'search', cmd: 'command', ask: 'ask' }[palMode];
}

function showCommands(q) {
  const s = q.toLowerCase();
  const research = s.startsWith('research ') ? s.slice(9).trim() : '';
  let list = COMMANDS.filter((c) => c.label.toLowerCase().includes(s) || c.id.includes(s));
  if (research) {
    list = [{ id: 'research', label: `Research “${research}”`, hint: 'gather → brain/raw/',
              run: () => runJob('research', '/api/run/research', { topic: research }) }];
  }
  palHits = list.map((c) => ({ cmd: c, title: c.label, layer: 'command', text: c.hint }));
  palSel = 0;
  paintHits('');
}

function showAskPrompt(q) {
  palHits = q
    ? [{ ask: q, title: `Ask: ${q}`, layer: 'ask', text: 'Enter to send · answers cite your notes' }]
    : [{ ask: '', title: 'Ask your vault…', layer: 'ask', text: 'type a question after ?' }];
  palSel = 0;
  paintHits('');
}

function showLocal(q) {
  const s = q.toLowerCase();
  const list = !s ? state.nodes.slice(0, 40)
    : state.nodes.filter((n) => n.title.toLowerCase().includes(s) ||
        n.path.toLowerCase().includes(s) || (n.tags || []).some((t) => t.includes(s)));
  palHits = list.slice(0, 40).map((n) => ({
    doc_id: n.id, title: n.title, layer: n.layer, text: n.excerpt, matched: 'name' }));
  palSel = 0;
  paintHits(s);
}

function scheduleSearch(v) {
  clearTimeout(palTimer);
  palTimer = setTimeout(async () => {
    if (!v.trim()) return;
    try {
      const r = await api('/api/search?k=25&q=' + encodeURIComponent(v));
      if ($('#q').value.trim() !== v.trim() || palMode !== 'search') return;
      if (r.hits.length) { palHits = r.hits; palSel = 0; paintHits(v, r.mode); }
    } catch { /* keep local results */ }
  }, 190);
}

function paintHits(q, mode) {
  const box = $('#hits');
  if (!palHits.length) {
    box.innerHTML = `<p class="empty">nothing matches “${q}”</p>`;
    $('#pal-hint').textContent = '';
    return;
  }
  const tidy = (s) => (s || '').trim().replace(/^\S*\s+/, (m) => (/^[A-Z(“"']/.test(m) ? m : '')).slice(0, 190);
  const words = q.trim().split(/\s+/).filter((w) => w.length > 2)
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const esc = (s) => (s || '').replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const hl = (s) => {
    let t = esc(s);
    for (const w of words) t = t.replace(new RegExp(`(${w})`, 'gi'), '<mark>$1</mark>');
    return t;
  };
  box.innerHTML = palHits.map((h, i) => `
    <button class="hit ${i === palSel ? 'sel' : ''}" data-idx="${i}">
      <span class="t"><b>${hl(h.title)}</b><span class="ly">${h.layer}</span>
        ${h.matched ? `<span class="mt">${h.matched}</span>` : ''}</span>
      <span class="s">${hl(tidy(h.text))}</span>
    </button>`).join('');
  $('#pal-hint').textContent = mode ? `${mode} · ${palHits.length}` : `${palHits.length}`;
  box.querySelector('.hit.sel')?.scrollIntoView({ block: 'nearest' });
}

function movePal(d) {
  if (!palHits.length) return;
  palSel = (palSel + d + palHits.length) % palHits.length;
  paintHits($('#q').value.replace(/^[>?]\s*/, ''));
}

function commitPal(i = palSel) {
  const h = palHits[i];
  if (!h) return;
  if (h.cmd) { closePalette(); h.cmd.run(); return; }
  if (h.ask !== undefined) { closePalette(); if (h.ask) ask(h.ask); else openAsk(); return; }
  openDoc(h.doc_id);
  closePalette();
}

/* ---------------------------------------------------------------------- ask */

let asking = false;

function openAsk() {
  $('#ask').classList.add('open');
  const t = $('#ask-q');
  t.focus();
  t.setSelectionRange(t.value.length, t.value.length);
}

async function ask(q) {
  if (!q.trim() || asking) return;
  asking = true;
  $('#ask').classList.add('open');
  $('#ask-q').value = q;
  const ans = $('#ask-answer');
  ans.innerHTML = '<span class="cursor-blink"></span>';
  $('#ask-sources').innerHTML = '';
  $('#ask .body').scrollTop = 0;
  state.sources = [];
  let buf = '';

  try {
    const r = await fetch('/api/ask', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ q }),
    });
    if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 160)}`);

    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let pending = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += dec.decode(value, { stream: true });
      const frames = pending.split('\n\n');
      pending = frames.pop();
      for (const f of frames) {
        const ev = /event:\s*(\w+)/.exec(f);
        const dm = /data:\s*([\s\S]*)$/.exec(f);
        if (!ev || !dm) continue;
        let data; try { data = JSON.parse(dm[1]); } catch { continue; }
        if (ev[1] === 'sources') { state.sources = data; renderSources(data); }
        else if (ev[1] === 'delta') {
          buf += data;
          const box = $('#ask .body');
          const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
          ans.innerHTML = citeify(md(buf)) + '<span class="cursor-blink"></span>';
          if (atBottom) box.scrollTop = box.scrollHeight;
        }
      }
    }
    ans.innerHTML = citeify(md(buf)) || '<p class="empty">no answer returned</p>';
    $('#ask .body').scrollTop = 0;
  } catch (e) {
    ans.innerHTML = `<p class="empty">ask failed: ${e.message}</p>`;
  } finally {
    asking = false;
  }
}

/* Turn "[3]" in the answer into a live chip bound to its source document. This
   is the link between the prose and the map: hovering it ignites the node the
   claim came from, so provenance is spatial instead of a path you have to read. */
function citeify(html) {
  return html.replace(/\[(\d{1,2})\]/g, (m, n) => {
    const s = state.sources[+n - 1];
    if (!s) return m;
    return `<span class="cite" data-cite="${s.doc_id}" tabindex="0"
      title="${s.title} — ${s.path}">${n}</span>`;
  });
}

function renderSources(list) {
  if (!list.length) {
    $('#ask-sources').innerHTML = '<h4>sources</h4><p class="empty">nothing retrieved</p>';
    return;
  }
  $('#ask-sources').innerHTML = '<h4>sources</h4>' + list.map((s) => {
    const h = s.heading && s.heading.trim().toLowerCase() !== s.title.trim().toLowerCase()
      ? ` <span class="dim">— ${s.heading}</span>` : '';
    return `<button class="src" data-open="${s.doc_id}" data-cite="${s.doc_id}">
      <span class="n">${s.n}</span>
      <span><b>${s.title}</b>${h}<br><span class="p">${s.path}</span></span></button>`;
  }).join('');
}

/* ------------------------------------------------------------------- jobs */

async function runJob(name, path, body) {
  const url = path || `/api/run/${name}`;
  toast(`${name}…`, 60000);
  try {
    const r = await api(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (r.ok === false) { toast(`${name} failed — see logs`); console.error(r); return; }
    const line = (r.stdout || '').trim().split('\n').filter(Boolean).pop();
    toast(line ? line.slice(0, 90) : `${name} done`);
    await refresh();
  } catch (e) {
    toast(`${name} failed: ${e.message}`);
  }
}

async function doSync() {
  toast('syncing…', 60000);
  try {
    const r = await api('/api/sync', { method: 'POST' });
    toast(`synced · ${r.index.docs} docs, ${r.index.vectors_total} vectors`);
    await refresh();
  } catch (e) { toast('sync failed: ' + e.message); }
}

async function refresh() {
  const [graph, status] = await Promise.all([
    api('/api/graph'), api('/api/status').catch(() => null)]);
  state.nodes = graph.nodes;
  state.byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
  state.titles = new Set(graph.nodes.map((n) => n.title.toLowerCase()));
  orbit.setData(graph.nodes, graph.edges);
  renderLegend();
  renderStatus(graph.stats, status);
}

/* ------------------------------------------------------------------ chrome */

let toastT = null;
function toast(msg, ms = 2400) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastT);
  toastT = setTimeout(() => t.classList.remove('show'), ms);
}

orbit.onSelect = (n) => openDoc(n.id, { move: false });
orbit.onHover = (n, x, y) => {
  const tip = $('#tip');
  if (!n) return tip.classList.remove('show');
  tip.innerHTML = `<b>${n.title}</b><span class="ly">${n.layer} · ${n.words} words${
    n.links?.length ? ` · ${n.links.length} links` : ''}</span>`;
  tip.style.left = Math.min(x + 14, innerWidth - 280) + 'px';
  tip.style.top = (y + 16) + 'px';
  tip.classList.add('show');
};

document.addEventListener('click', (e) => {
  const t = e.target.closest('[data-open],[data-ring],[data-copy],[data-wl],[data-act],[data-idx],.x');
  if (!t) return;
  if (t.dataset.idx !== undefined) { commitPal(+t.dataset.idx); return; }
  if (t.dataset.open) { openDoc(t.dataset.open); closePalette(); return; }
  if (t.dataset.wl) { jumpToTitle(t.dataset.wl); return; }
  if (t.dataset.ring) { orbit.toggleRing(t.dataset.ring); t.classList.toggle('off'); return; }
  if (t.dataset.copy) {
    navigator.clipboard?.writeText(t.dataset.copy)
      .then(() => toast('path copied')).catch(() => toast('copy blocked'));
    return;
  }
  if (t.classList.contains('x')) {
    const p = t.closest('.panel');
    p.classList.remove('open');
    if (p.id === 'doc') orbit.clearFocus();
    return;
  }
  switch (t.dataset.act) {
    case 'search': openPalette(); break;
    case 'cmd': openPalette('> '); break;
    case 'ask': openAsk(); break;
    case 'send': ask($('#ask-q').value); break;
    case 'reset': orbit.reset(); toast('view reset'); break;
    case 'help': $('#help').classList.toggle('open'); break;
  }
});

/* Citation ⇄ map. Hovering a chip or a source row lights the node it refers to. */
document.addEventListener('pointerover', (e) => {
  const c = e.target.closest('[data-cite]');
  if (c) orbit.ignite(c.dataset.cite);
});
document.addEventListener('pointerout', (e) => {
  if (e.target.closest('[data-cite]') && !$('#doc').classList.contains('open')) {
    orbit.clearFocus();
  }
});
document.addEventListener('focusin', (e) => {
  const c = e.target.closest('[data-cite]');
  if (c) orbit.ignite(c.dataset.cite);
});

$('#q').addEventListener('input', (e) => route(e.target.value));
$('#q').addEventListener('keydown', (e) => {
  if (e.key === 'ArrowDown') { e.preventDefault(); movePal(1); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); movePal(-1); }
  else if (e.key === 'Tab') { e.preventDefault(); movePal(e.shiftKey ? -1 : 1); }
  else if (e.key === 'Enter') {
    e.preventDefault();
    const raw = $('#q').value.trim();
    if (e.shiftKey && palMode === 'search' && raw) { closePalette(); ask(raw); return; }
    commitPal();
  }
});

$('#ask-q').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); ask(e.target.value); }
});

document.addEventListener('keydown', (e) => {
  const typing = /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName);
  if (e.key === 'Escape') {
    closePalette();
    $$('.panel.open').forEach((p) => { if (p.id !== 'palette') p.classList.remove('open'); });
    orbit.clearFocus();
    return;
  }
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault(); openPalette(); return;
  }
  if (typing) return;
  if (e.key === '/') { e.preventDefault(); openPalette(); }
  // Accept both the produced character and the physical key: on some layouts and
  // in automated browsers `>` arrives as Shift+Period rather than as '>'.
  else if (e.key === '>' || (e.shiftKey && e.code === 'Period')) {
    e.preventDefault(); openPalette('> ');
  }
  else if (e.key === '?' || (e.shiftKey && e.code === 'Slash')) {
    e.preventDefault(); $('#help').classList.toggle('open');
  }
  else if (e.key === 'a') { e.preventDefault(); openAsk(); }
  else if (e.key === 'r') { e.preventDefault(); runJob('radar'); }
  else if (e.key === '0') orbit.reset();
  else if (e.key === '+' || e.key === '=') orbit.zoom(1.25);
  else if (e.key === '-') orbit.zoom(1 / 1.25);
});

// Exposed deliberately: single-user private instance, and being able to poke the
// renderer from the console is worth more here than namespace purity.
window.__agentos = { orbit, state, ask, openDoc, runJob };

boot();
