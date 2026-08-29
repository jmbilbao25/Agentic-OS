/* AgentOS second brain — UI wiring.
 * Orbit map + command palette + doc preview + streaming RAG answers.
 */
import { Orbit, RINGS } from './orbit.js';
import { md } from './md.js';

const $ = (s) => document.querySelector(s);
const api = async (p, o) => {
  const r = await fetch(p, o);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
};

const state = { nodes: [], byId: {}, titles: new Set(), status: null, sel: null };

const orbit = new Orbit($('#stage'));

/* ------------------------------------------------------------------ boot */

async function boot() {
  try {
    const [graph, status] = await Promise.all([
      api('/api/graph'), api('/api/status').catch(() => null),
    ]);
    state.nodes = graph.nodes;
    state.byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
    state.titles = new Set(graph.nodes.map((n) => n.title.toLowerCase()));
    state.status = status;

    orbit.setData(graph.nodes, graph.edges);
    orbit.start();

    renderLegend();
    renderStatus(graph.stats, status);
    if (graph.missing.length) console.info('unresolved wikilinks', graph.missing);
  } catch (e) {
    $('#stage').insertAdjacentHTML('afterend',
      `<div class="banner show">Failed to load the vault: <code>${e.message}</code></div>`);
  }
}

function renderLegend() {
  $('#legend').innerHTML = RINGS.slice().reverse().map((r) => `
    <button data-ring="${r.id}" style="color:${r.color}">
      <i class="sw"></i><span>${r.label}</span>
      <span class="n">${r.count}</span>
    </button>`).join('');
}

function renderStatus(stats, status) {
  const idx = status && status.index || {};
  const mode = (idx.meta && idx.meta.mode) || 'keyword';
  $('#status').innerHTML = `
    <span class="pill ${mode}">${mode}</span>
    <span>${stats.docs} docs</span>
    <span>${idx.chunks || 0} chunks</span>
    <span>${idx.vectors || 0} vectors</span>`;

  const probs = (status && status.problems) || [];
  if (probs.length) {
    $('#banner').innerHTML = probs.map((p) => `<span>${p}</span>`).join(' · ');
    $('#banner').classList.add('show');
    setTimeout(() => $('#banner').classList.remove('show'), 9000);
  }
}

/* ------------------------------------------------------------- doc panel */

async function openDoc(id) {
  const node = state.byId[id];
  if (!node) return;
  state.sel = id;
  orbit.focus(id);
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
    $('#doc-body').innerHTML = `
      <div class="meta"><span class="tag">${doc.layer}</span>${tags}${fm}</div>
      <div class="pathrow"><code>${doc.path}</code>
        <button data-copy="${doc.path}">copy</button></div>
      <div class="md">${md(doc.body, { exists: (n) => state.titles.has(n.toLowerCase()) })}</div>`;
    $('#doc .body').scrollTop = 0;
  } catch (e) {
    $('#doc-body').innerHTML = `<p class="empty">could not load: ${e.message}</p>`;
  }
}

function jumpToTitle(title) {
  const n = state.nodes.find((x) => x.title.toLowerCase() === title.toLowerCase());
  if (n) openDoc(n.id);
  else toast(`no note named "${title}"`);
}

/* --------------------------------------------------------------- palette */

let palTimer = null, palHits = [], palSel = 0;

function openPalette(seed = '') {
  $('#palette').classList.add('open');
  const inp = $('#q');
  inp.value = seed;
  inp.focus();
  inp.select();
  seed ? runSearch(seed) : showLocal('');
}

function closePalette() { $('#palette').classList.remove('open'); }

/* Instant local filter on titles/paths/tags so typing always feels immediate;
   the server's hybrid search lands a moment later and replaces it. */
function showLocal(q) {
  const s = q.trim().toLowerCase();
  const list = !s ? state.nodes.slice(0, 40)
    : state.nodes.filter((n) =>
        n.title.toLowerCase().includes(s) || n.path.toLowerCase().includes(s) ||
        (n.tags || []).some((t) => t.includes(s)));
  palHits = list.slice(0, 40).map((n) => ({
    doc_id: n.id, title: n.title, layer: n.layer, path: n.path,
    text: n.excerpt, matched: 'name',
  }));
  palSel = 0;
  paintHits(s);
}

async function runSearch(q) {
  if (!q.trim()) return showLocal('');
  showLocal(q);                                  // optimistic
  try {
    const r = await api('/api/search?k=25&q=' + encodeURIComponent(q));
    if ($('#q').value.trim() !== q.trim()) return;   // stale response
    if (r.hits.length) {
      palHits = r.hits; palSel = 0; paintHits(q, r.mode);
    }
  } catch { /* keep the local results */ }
}

function paintHits(q, mode) {
  const box = $('#hits');
  if (!palHits.length) {
    box.innerHTML = `<p class="empty">nothing matches “${q}”</p>`;
    return;
  }
  // Chunks are split mid-sentence, so a raw excerpt often opens on a word
  // fragment ("x as disposable…"). Drop the partial first word.
  const tidy = (s) => {
    let t = (s || '').trim().replace(/^\S*\s+/, (m) => (/^[A-Z(“"']/.test(m) ? m : ''));
    return t.slice(0, 200);
  };
  const words = q.trim().split(/\s+/).filter((w) => w.length > 2)
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const hl = (s) => {
    let t = (s || '').replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
    for (const w of words) t = t.replace(new RegExp(`(${w})`, 'gi'), '<mark>$1</mark>');
    return t;
  };
  box.innerHTML = palHits.map((h, i) => `
    <button class="hit ${i === palSel ? 'sel' : ''}" data-open="${h.doc_id}">
      <span class="t"><b>${hl(h.title)}</b><span class="ly">${h.layer}</span>
        <span class="mt">${h.matched || ''}</span></span>
      <span class="s">${hl(tidy(h.text))}</span>
    </button>`).join('');
  $('#pal-hint').textContent = mode ? `${mode} · ${palHits.length}` : `${palHits.length}`;
  const sel = box.querySelector('.hit.sel');
  if (sel) sel.scrollIntoView({ block: 'nearest' });
}

function movePal(d) {
  if (!palHits.length) return;
  palSel = (palSel + d + palHits.length) % palHits.length;
  paintHits($('#q').value);
}

/* ------------------------------------------------------------------- ask */

let asking = false;

async function ask(q) {
  if (!q.trim() || asking) return;
  asking = true;
  $('#ask').classList.add('open');
  const ans = $('#ask-answer');
  const srcBox = $('#ask-sources');
  ans.innerHTML = '<span class="cursor-blink"></span>';
  srcBox.innerHTML = '';
  let buf = '';

  try {
    const r = await fetch('/api/ask', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ q }),
    });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);

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
        if (ev[1] === 'sources') renderSources(data);
        else if (ev[1] === 'delta') {
          buf += data;
          ans.innerHTML = md(buf) + '<span class="cursor-blink"></span>';
          $('#ask .body').scrollTop = $('#ask .body').scrollHeight;
        }
      }
    }
    ans.innerHTML = md(buf) || '<p class="empty">no answer returned</p>';
  } catch (e) {
    ans.innerHTML = `<p class="empty">ask failed: ${e.message}</p>`;
  } finally {
    asking = false;
  }
}

function renderSources(list) {
  if (!list.length) {
    $('#ask-sources').innerHTML =
      '<h4>sources</h4><p class="empty">nothing retrieved</p>';
    return;
  }
  $('#ask-sources').innerHTML = '<h4>sources</h4>' + list.map((s) => `
    <button class="src" data-open="${s.doc_id}">
      <span class="n">${s.n}</span>
      <span><b>${s.title}</b> — ${s.heading || ''}<br>
        <span style="font-size:11px;color:var(--dimmer)">${s.path}</span></span>
    </button>`).join('');
}

/* ----------------------------------------------------------------- misc */

let toastT = null;
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastT);
  toastT = setTimeout(() => t.classList.remove('show'), 2200);
}

orbit.onSelect = (n) => openDoc(n.id);
orbit.onHover = (n, x, y) => {
  const tip = $('#tip');
  if (!n) return tip.classList.remove('show');
  tip.innerHTML = `<b>${n.title}</b><span class="ly">${n.layer} · ${n.words} words</span>`;
  tip.style.left = Math.min(x + 14, innerWidth - 280) + 'px';
  tip.style.top = (y + 16) + 'px';
  tip.classList.add('show');
};

/* --------------------------------------------------------------- events */

document.addEventListener('click', (e) => {
  const t = e.target.closest('[data-open],[data-ring],[data-copy],[data-wl],[data-act],.x');

  if (!t) return;
  if (t.dataset.open) { openDoc(t.dataset.open); closePalette(); return; }
  if (t.dataset.wl) { jumpToTitle(t.dataset.wl); return; }
  if (t.dataset.ring) {
    orbit.toggleRing(t.dataset.ring);
    t.classList.toggle('off');
    return;
  }
  if (t.dataset.copy) {
    navigator.clipboard?.writeText(t.dataset.copy)
      .then(() => toast('path copied')).catch(() => toast('copy blocked'));
    return;
  }
  if (t.classList.contains('x')) { t.closest('.panel').classList.remove('open'); return; }

  switch (t.dataset.act) {
    case 'search': openPalette(); break;
    case 'ask': $('#ask').classList.add('open'); $('#ask-q').focus(); break;
    case 'send': ask($('#ask-q').value); break;
    case 'reset': orbit.reset(); toast('view reset'); break;
    case 'zin': orbit.zoom(1.25); break;
    case 'zout': orbit.zoom(1 / 1.25); break;
    case 'sync':
      toast('syncing…');
      api('/api/sync', { method: 'POST' })
        .then((r) => { toast(`reindexed ${r.index.docs} docs`); boot(); })
        .catch((e) => toast('sync failed: ' + e.message));
      break;
    case 'help': $('#help').classList.toggle('open'); break;
  }
});

$('#q').addEventListener('input', (e) => {
  const v = e.target.value;
  showLocal(v);
  clearTimeout(palTimer);
  palTimer = setTimeout(() => runSearch(v), 190);
});

$('#q').addEventListener('keydown', (e) => {
  if (e.key === 'ArrowDown') { e.preventDefault(); movePal(1); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); movePal(-1); }
  else if (e.key === 'Enter') {
    e.preventDefault();
    if (e.shiftKey) { closePalette(); ask($('#q').value); return; }
    const h = palHits[palSel];
    if (h) { openDoc(h.doc_id); closePalette(); }
  }
});

$('#ask-q').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); ask(e.target.value); }
});

document.addEventListener('keydown', (e) => {
  const typing = /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName);
  if (e.key === 'Escape') {
    closePalette();
    document.querySelectorAll('.panel.open').forEach((p) => {
      if (p.id !== 'palette') p.classList.remove('open');
    });
    return;
  }
  if (typing) return;
  if (e.key === '/') { e.preventDefault(); openPalette(); }
  else if (e.key === 'a') { $('#ask').classList.add('open'); $('#ask-q').focus(); }
  else if (e.key === '?') $('#help').classList.toggle('open');
  else if (e.key === '0') orbit.reset();
  else if (e.key === '+' || e.key === '=') orbit.zoom(1.25);
  else if (e.key === '-') orbit.zoom(1 / 1.25);
});

boot();
