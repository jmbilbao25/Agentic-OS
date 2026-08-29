/* AgentOS second brain — wiring.
 *
 * This file owns nothing but connections: the map, the dock, the palette and the
 * four views are each self-contained, and everything here is the plumbing between
 * them plus the global keyboard map.
 */

import { get, post, AuthLost } from './api.js';
import { Orbit, RINGS } from './orbit.js';
import { LAYOUTS } from './layouts.js';
import { Palette } from './palette.js';
import { ModelPicker, setCatalogue } from './models.js';
import { DocView, AskView } from './views.js';
import { GauntletView } from './gauntlet.js';
import { SettingsView } from './settings.js';

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const state = {
  nodes: [], byId: {}, titles: new Set(), stats: null, status: null,
  filter: null, busy: false,
};

const orbit = new Orbit($('#stage'));

/* -------------------------------------------------------------------- toast */

let toastSeq = 0;
function toast(msg, kind = '') {
  const id = ++toastSeq;
  const icon = kind === 'err' ? 'i-alert' : kind === 'ok' ? 'i-check' : 'i-doc';
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.innerHTML = `<svg class="i" aria-hidden="true"><use href="#${icon}"/></svg>
    <span>${esc(msg)}</span>`;
  $('#toasts').append(el);
  setTimeout(() => {
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 220);
  }, kind === 'err' ? 6200 : 3000);
  return id;
}

/** A lost session is not recoverable in place; send them to the login page. */
function handle(e) {
  if (e instanceof AuthLost) {
    toast('Session expired — signing you back in', 'err');
    setTimeout(() => { window.location.href = '/auth/login'; }, 700);
    return;
  }
  console.error(e);
  toast(e.message || String(e), 'err');
}

const guard = (fn) => (...a) => { try { const r = fn(...a); if (r?.catch) r.catch(handle); } catch (e) { handle(e); } };

/* --------------------------------------------------------------------- dock */

const dock = $('#dock');
let activeTab = null;

function openTab(name) {
  activeTab = name;
  dock.classList.add('open');
  dock.classList.toggle('wide', name === 'gauntlet' || name === 'settings');
  document.querySelectorAll('.tab').forEach((t) =>
    t.setAttribute('aria-selected', String(t.dataset.tab === name)));
  document.querySelectorAll('.view').forEach((v) =>
    v.classList.toggle('active', v.id === `view-${name}`));

  if (name === 'settings') settings.load().catch(handle);
  if (name === 'ask') setTimeout(() => askView.focus(), 60);
  syncChrome();
}

function closeDock() {
  dock.classList.remove('open');
  activeTab = null;
  orbit.deselect();
  syncChrome();
  releaseFocus();
}

/* Hand focus back to the document.
 *
 * Every single-key shortcut is suppressed while focus sits in a field, which is
 * correct — but closing a panel used to leave the caret inside whatever input you
 * touched last, so `/`, `j`, `0` and the rest silently stopped working and the
 * only cure was clicking the background. Closing a surface has to also give the
 * keyboard back.
 */
function releaseFocus() {
  const el = document.activeElement;
  if (el && el !== document.body && typeof el.blur === 'function') el.blur();
}

/* Drag-to-resize, persisted. A dock you cannot widen is a dock you stop using
   for anything longer than a paragraph. */
(function resizable() {
  const grip = $('#dock-grip');
  const saved = Number(localStorage.getItem('agentos.dockWidth'));
  if (saved >= 320) document.documentElement.style.setProperty('--dock-w', `${saved}px`);

  let from = null;
  grip.addEventListener('pointerdown', (e) => {
    from = { x: e.clientX, w: dock.getBoundingClientRect().width };
    grip.classList.add('dragging');
    grip.setPointerCapture(e.pointerId);
  });
  grip.addEventListener('pointermove', (e) => {
    if (!from) return;
    const w = Math.max(320, Math.min(window.innerWidth - 80, from.w - (e.clientX - from.x)));
    dock.classList.remove('wide');
    document.documentElement.style.setProperty('--dock-w', `${w}px`);
  });
  grip.addEventListener('pointerup', () => {
    if (!from) return;
    from = null;
    grip.classList.remove('dragging');
    localStorage.setItem('agentos.dockWidth',
      String(Math.round(dock.getBoundingClientRect().width)));
    syncChrome();
  });
})();

/* -------------------------------------------------------------------- views */

const askModel = new ModelPicker($('#ask-model-combo'),
  { blank: 'Use the saved model', onChange: () => {} });
const gBuilder = new ModelPicker($('#g-builder-combo'),
  { blank: 'Use the saved builder' });
const gCritic = new ModelPicker($('#g-critic-combo'),
  { blank: 'Use the saved critic' });

const setBusy = (b) => { state.busy = b; };

/* Keyboard hints, written for the platform actually in front of you.
 *
 * The obvious ⌘/↵ glyphs are a trap: U+2318 and U+21B5 are outside the latin
 * subset of the bundled face *and* missing from the default Linux monospace, so
 * they shipped as empty boxes on anything that was not a Mac. Words render
 * everywhere. */
const IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
document.querySelectorAll('[data-kbd="send"]').forEach((el) => {
  el.textContent = IS_MAC ? 'Cmd Enter' : 'Ctrl Enter';
});

const docView = new DocView({
  titles: () => state.titles,
  toast,
  onJump: guard(({ id, title }) => {
    if (id) return openDoc(id);
    const n = state.nodes.find((x) => x.title.toLowerCase() === title.toLowerCase());
    if (n) openDoc(n.id);
    else toast(`No note named “${title}” yet`, 'err');
  }),
});

const askView = new AskView({
  onOpenDoc: guard(openDoc), modelPicker: askModel, toast, onBusy: setBusy,
});

const gauntletView = new GauntletView({
  builderPicker: gBuilder, criticPicker: gCritic, toast,
  onOpenDoc: guard(openDoc), onBusy: setBusy,
});

const settings = new SettingsView({
  toast,
  onSaved: guard(async () => {
    await refreshStatus();
    await loadModels(true);
  }),
});

/* --------------------------------------------------------------------- docs */

async function openDoc(id) {
  if (!id) return;
  orbit.focus(id);
  openTab('doc');
  await docView.load(id);
}

function askAbout(q) {
  openTab('ask');
  askView.setQuestion(q);
  askView.ask(q).catch(handle);
}

/* -------------------------------------------------------------------- rail */

function renderRings() {
  $('#rings').innerHTML = RINGS.slice().reverse().map((r) => `
    <button class="ring-btn" data-ring="${r.id}" aria-pressed="true"
            title="Click to hide · shift-click to isolate">
      <i class="sw"></i><span class="lbl">${r.label}</span>
      <span class="n">${r.count}</span>
    </button>`).join('');
  // The swatch inherits currentColor, so the ring's own hue has to be set on the
  // button. Done here rather than in CSS because the palette lives in orbit.js.
  document.querySelectorAll('.ring-btn').forEach((b) => {
    const ring = RINGS.find((r) => r.id === b.dataset.ring);
    if (ring) b.style.color = ring.color;
  });
}

/* Layout switcher.
 *
 * The chosen layout is persisted, because it is a way of working rather than a
 * momentary action: someone who thinks in a ranked list should not be handed the
 * rings again on every visit. */
const LAYOUT_KEY = 'agentos.layout';

function renderLayouts() {
  $('#layouts').innerHTML = LAYOUTS.map((l, i) => `
    <button class="layout-btn" data-layout="${l.id}"
            aria-pressed="${String(l.id === orbit.layout)}"
            title="${esc(l.label)} — ${esc(l.hint)} (${i + 1})">
      <svg class="i" aria-hidden="true"><use href="#i-lay-${l.id}"/></svg>
      <span class="lbl">${esc(l.label)}</span>
    </button>`).join('');
  // Rank is the one layout whose meaning depends on state outside itself, so it
  // says what it is currently ordered by instead of describing itself in general.
  const l = LAYOUTS.find((x) => x.id === orbit.layout);
  const n = orbit.ranking.length;
  $('#layout-hint').textContent = orbit.layout !== 'rank' ? (l?.hint || '')
    : n ? `${n} match${n === 1 ? '' : 'es'}, best first`
        : 'press / and search — the line follows the results';
}

function setLayout(id, { animate = true } = {}) {
  if (orbit.setLayout(id, { animate }) !== id) return;
  localStorage.setItem(LAYOUT_KEY, id);
  renderLayouts();
}

/* Tell the map what is sitting on top of it.
 *
 * The canvas fills the window and the rail and topbar float over its left and top
 * edges. The rings never cared — a circle centred in the window looks centred
 * whatever overlaps it — but a horizontal line does: centred in the window it runs
 * straight under the rail, and the first version of Rank lost its five best
 * results behind the legend. Measured from the DOM rather than hardcoded, because
 * the rail is hidden on narrow viewports and the dock is resizable.
 *
 * The dock is deliberately excluded. It overlays the right-hand side, but
 * reflowing the entire map every time you open a note would be far more
 * disorienting than a few dots being covered while you read. */
function syncChrome() {
  const gap = 16;
  const pad = 6;
  const box = (sel) => {
    const el = $(sel);
    if (!el || el.hidden) return null;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 ? r : null;
  };
  const rail = box('.rail');
  const bar = box('header');

  orbit.setInsets({
    left: rail ? rail.right + gap : gap,
    right: gap,
    top: bar ? bar.bottom + gap : gap,
    bottom: gap,
  });

  // Labels get the exact shapes rather than the per-edge insets, so the empty
  // corner above the rail stays usable. The dock is included here but not in the
  // insets: hiding a label behind it is a small loss, reflowing the whole map
  // every time a note opens is a large one.
  const open = dock.classList.contains('open') ? box('#dock') : null;
  orbit.setObstacles([rail, bar, open].filter(Boolean).map((r) => ({
    x: r.left - pad, y: r.top - pad, w: r.width + pad * 2, h: r.height + pad * 2,
  })));
}

function syncRingButtons() {
  document.querySelectorAll('.ring-btn').forEach((b) => {
    b.setAttribute('aria-pressed', String(orbit.ringVisible(b.dataset.ring)));
  });
  updateCounts();
}

function updateCounts() {
  $('#scrub-count').textContent = `${orbit.visibleCount()} / ${state.nodes.length}`;
}

/* Recency scrubber.
 *
 * The scale is deliberately non-linear. A vault's edits cluster in the last few
 * weeks, so a linear slider spends most of its travel inside a span nobody
 * touched and then jumps from "everything" to "nothing" in the last few pixels.
 * Raising the fraction to a power puts the resolution where the notes are.
 *
 * Slider at 100 means no filter at all, not "the newest instant".
 */
function setupScrubber() {
  const el = $('#scrub');
  const label = $('#scrub-label');

  const apply = () => {
    const v = Number(el.value);
    if (v >= 100) {
      orbit.setSince(0);
      label.textContent = 'everything';
    } else {
      const { oldest, newest } = orbit;
      const span = Math.max(1, newest - oldest);
      // v=0 -> cut at newest (almost nothing shown); v=100 -> cut at oldest.
      const reach = (v / 100) ** 0.45;          // eased window width
      const cut = newest - span * reach;
      orbit.setSince(cut);
      const days = Math.max(0, Math.round((Date.now() / 1000 - cut) / 86400));
      label.textContent = days <= 1 ? 'today only' : `last ${days} days`;
    }
    updateCounts();
  };

  el.addEventListener('input', apply);
  apply();
}

function setFilter(f) {
  state.filter = f;
  const block = $('#filter-block');
  if (!f) {
    orbit.setPredicate(null);
    block.hidden = true;
    updateCounts();
    return;
  }
  if (f.tag) orbit.setPredicate((n) => (n.tags || []).includes(f.tag));
  else if (f.layer) orbit.setPredicate((n) => n.layer === f.layer);

  block.hidden = false;
  $('#filter-chips').innerHTML = `
    <button class="chip layer" data-act="clear-filter" title="Clear filter">
      ${f.tag ? `#${esc(f.tag)}` : `@${esc(f.layer)}`} ✕</button>`;
  const n = orbit.visibleCount();
  updateCounts();
  toast(n ? `${n} note${n === 1 ? '' : 's'} match` : 'Nothing matches that filter',
        n ? '' : 'err');
}

/* ---------------------------------------------------------------- telemetry */

function renderTelemetry() {
  const idx = state.status?.index || {};
  const mode = idx.meta?.mode || 'keyword';
  const live = state.status?.llm_configured;
  $('#telemetry').innerHTML = `
    <span class="pill ${esc(mode)}">${esc(mode)}</span>
    <span><b>${state.stats?.docs ?? 0}</b> notes</span>
    <span><b>${idx.chunks ?? 0}</b> chunks</span>
    <span><b>${idx.vectors ?? 0}</b> vectors</span>
    <span class="pill ${live ? 'live' : 'off'}">${live
      ? esc(shortModel(state.status.model)) : 'no key'}</span>`;
}

const shortModel = (m) => (m || '').split('/').pop() || m || '';

function renderNotices() {
  const probs = state.status?.problems || [];
  const box = $('#notices');
  if (!probs.length) { box.innerHTML = ''; return; }
  box.innerHTML = probs.map((p, i) => `
    <div class="notice">
      <svg class="i" aria-hidden="true"><use href="#i-warn"/></svg>
      <span>${esc(p)}</span>
      <button data-dismiss="${i}" aria-label="Dismiss">
        <svg class="i" aria-hidden="true"><use href="#i-x"/></svg></button>
    </div>`).join('');
}

/* --------------------------------------------------------------------- boot */

async function loadGraph() {
  const graph = await get('/api/graph');
  state.nodes = graph.nodes;
  state.byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
  state.titles = new Set(graph.nodes.map((n) => n.title.toLowerCase()));
  state.stats = graph.stats;
  orbit.setData(graph.nodes, graph.edges);
  renderRings();
  renderLayouts();
  syncRingButtons();
  if (graph.missing.length) {
    console.info('Unresolved wikilinks:', graph.missing);
  }
}

async function refreshStatus() {
  state.status = await get('/api/status').catch(() => null);
  if (!state.status) return;
  renderTelemetry();
  renderNotices();
  orbit.configure({
    reducedMotion: state.status.ui?.reduced_motion,
    spin: state.status.ui?.orbit_spin,
    labelDensity: state.status.ui?.label_density,
  });
  document.body.classList.toggle('reduced-motion',
    !!state.status.ui?.reduced_motion);
  gauntletView.setDefaults(state.status.gauntlet);
  if (state.status.gauntlet) {
    if (!gBuilder.value) gBuilder.input.placeholder =
      `Use the saved builder · ${shortModel(state.status.gauntlet.builder)}`;
    if (!gCritic.value) gCritic.input.placeholder =
      `Use the saved critic · ${shortModel(state.status.gauntlet.critic)}`;
  }
  if (state.status.model) {
    askModel.input.placeholder = `Use the saved model · ${shortModel(state.status.model)}`;
  }
}

async function loadModels(force = false) {
  try {
    const r = await get(`/api/models${force ? '?refresh=true' : ''}`);
    setCatalogue(r.models || []);
    if (r.error) console.info('model catalogue:', r.error);
  } catch (e) {
    if (e instanceof AuthLost) throw e;
    console.info('model catalogue unavailable:', e.message);
  }
}

async function boot() {
  try {
    // Before the graph loads, so the first frame is already in the right shape.
    const saved = localStorage.getItem(LAYOUT_KEY);
    if (saved) orbit.setLayout(saved, { animate: false });
    await loadGraph();
    syncChrome();
    orbit.start();
    setupScrubber();
    // The rail's height depends on the ring counts, which only exist after the
    // graph loads, and on fonts, which land later still.
    requestAnimationFrame(syncChrome);
    window.addEventListener('resize', syncChrome);
    if (document.fonts?.ready) document.fonts.ready.then(syncChrome);
    await refreshStatus();
    loadModels().catch(() => {});
  } catch (e) {
    handle(e);
    $('#notices').innerHTML = `<div class="notice">
      <svg class="i" aria-hidden="true"><use href="#i-warn"/></svg>
      <span>Could not load the vault: ${esc(e.message)}</span></div>`;
  }
}

/* ------------------------------------------------------------------ palette */

const commands = () => [
  { label: 'Ask the vault', hint: 'Retrieval-grounded answer', keys: 'A',
    run: () => { openTab('ask'); askView.focus(); } },
  { label: 'Run a gauntlet', hint: 'Builder vs critic against a real bar',
    keys: 'G', run: () => openTab('gauntlet') },
  { label: 'Settings', hint: 'Model, provider, retrieval, interface', keys: ',',
    run: () => openTab('settings') },
  { label: 'Sync from git', hint: 'git pull, then reindex',
    run: guard(doSync) },
  { label: 'Reindex', hint: 'Incremental rebuild of the search index',
    run: guard(() => doReindex(false)) },
  { label: 'Full reindex', hint: 'Rebuild every chunk and vector from scratch',
    run: guard(() => doReindex(true)) },
  ...LAYOUTS.map((l, i) => ({
    label: `Layout: ${l.label}`, hint: l.hint, keys: String(i + 1),
    run: () => setLayout(l.id),
  })),
  { label: 'Reset the view', hint: 'Recentre and unfreeze the map', keys: '0',
    run: () => { orbit.reset(); closeDock(); } },
  { label: 'Show every ring', hint: 'Undo any ring isolation',
    run: () => { orbit.showAllRings(); syncRingButtons(); } },
  { label: 'Clear filters', hint: 'Drop the tag, layer, recency and search order',
    run: () => { setFilter(null); $('#scrub').value = 100;
                 orbit.setSince(0); $('#scrub-label').textContent = 'everything';
                 orbit.clearHighlight(); renderLayouts(); updateCounts(); } },
  { label: 'Copy vault statistics', hint: 'Counts as JSON',
    run: () => navigator.clipboard?.writeText(JSON.stringify(state.stats, null, 2))
      .then(() => toast('Statistics copied'))
      .catch(() => toast('The browser blocked the clipboard', 'err')) },
  { label: 'Sign out', hint: 'End this session', keys: '',
    run: () => { window.location.href = '/auth/logout'; } },
];

const palette = new Palette({
  onOpenDoc: guard(openDoc),
  onAsk: guard(askAbout),
  onFilter: guard(setFilter),
  commands,
  nodes: () => state.nodes,
});

/* Search results light up on the map, so the palette and the map are one view of
   the same query rather than two unrelated surfaces.
 *
 * Capped at 12: beyond that "the results" stops being a shape you can read and
 * becomes most of the vault. And the highlight is cleared when the palette closes
 * — it used to persist for the rest of the session, so the map stayed marked up
 * with a query you had already forgotten. */
const paintOrig = palette.paint.bind(palette);
palette.paint = (rows, q, mode) => {
  paintOrig(rows, q, mode);
  if (palette.mode === 'find' && q) {
    orbit.highlight(rows.filter((r) => r.kind === 'doc').map((r) => r.id).slice(0, 12));
  } else {
    orbit.clearHighlight();
  }
  renderLayouts();      // the Rank hint reports the live match count
};

/* Closing the finder drops the highlight — except in Rank, where the result order
 * is not decoration on top of the map, it *is* the map. Clearing it there would
 * re-sort every node back to alphabetical the instant you stopped typing, which
 * makes the layout unusable for the thing it exists to do. Emptying the search
 * box still clears it, via the paint hook above. */
palette.onClose = () => {
  if (orbit.layout === 'rank') orbit.clearPulse();
  else orbit.clearHighlight();
  renderLayouts();
  releaseFocus();
};

/* ------------------------------------------------------------------ actions */

async function doSync() {
  toast('Pulling from git…');
  const r = await post('/api/sync');
  if (!r.pull_ok) toast(`git pull failed: ${r.pull}`, 'err');
  await loadGraph();
  await refreshStatus();
  toast(`Reindexed ${r.index.docs} notes · ${r.index.chunks_total} chunks`, 'ok');
}

async function doReindex(full) {
  toast(full ? 'Full reindex…' : 'Reindexing…');
  const r = await post(`/api/reindex${full ? '?full=true' : ''}`);
  await loadGraph();
  await refreshStatus();
  toast(`${r.mode} · ${r.docs} notes · ${r.chunks_total} chunks · ${
    r.vectors_total} vectors`, 'ok');
}

/* ------------------------------------------------------------------- events */

document.addEventListener('click', (e) => {
  const t = e.target.closest(
    '[data-act],[data-tab],[data-ring],[data-layout],[data-dismiss]');
  if (!t) return;

  if (t.dataset.tab) return openTab(t.dataset.tab);

  if (t.dataset.layout) return setLayout(t.dataset.layout);

  if (t.dataset.ring) {
    if (e.shiftKey) orbit.soloRing(t.dataset.ring);
    else orbit.toggleRing(t.dataset.ring);
    return syncRingButtons();
  }

  if (t.dataset.dismiss !== undefined) return t.closest('.notice')?.remove();

  switch (t.dataset.act) {
    case 'palette': palette.toggle(); break;
    case 'ask': openTab('ask'); askView.focus(); break;
    case 'gauntlet': openTab('gauntlet'); break;
    case 'settings': openTab('settings'); break;
    case 'close-dock': closeDock(); break;
    case 'ask-send': askView.ask().catch(handle); break;
    case 'fetch-bar': gauntletView.fetchBar().catch(handle); break;
    case 'gauntlet-run': gauntletView.run().catch(handle); break;
    case 'gauntlet-stop': gauntletView.stop(); break;
    case 'settings-save': settings.save().catch(handle); break;
    case 'settings-reset': settings.resetAll().catch(handle); break;
    case 'clear-filter': setFilter(null); break;
    default: break;
  }
});

$('#ask-q').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
    e.preventDefault();
    askView.ask().catch(handle);
  }
});

$('#g-goal').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
    e.preventDefault();
    gauntletView.run().catch(handle);
  }
});

orbit.onSelect = guard((n) => {
  if (!n) { if (activeTab === 'doc') closeDock(); return; }
  openDoc(n.id);
});

orbit.onHover = (n, x, y) => {
  const tip = $('#tip');
  if (!n) { tip.classList.remove('show'); tip.setAttribute('aria-hidden', 'true'); return; }
  tip.innerHTML = `<b>${esc(n.title)}</b>
    <span class="meta">${esc(n.layer)} · ${n.words} words · ${
      n.backlinks || 0} in</span>
    ${n.excerpt ? `<span class="snip">${esc(n.excerpt.slice(0, 140))}…</span>` : ''}`;
  // Flip before the edge rather than after: a tooltip that hangs off-screen is
  // worse than one that appears on the other side of the cursor.
  const w = 280, h = tip.offsetHeight || 90;
  tip.style.left = `${Math.min(x + 14, window.innerWidth - w - 12)}px`;
  tip.style.top = `${y + 16 + h > window.innerHeight ? y - h - 12 : y + 16}px`;
  tip.classList.add('show');
  tip.setAttribute('aria-hidden', 'false');
};

/* Which controls should swallow a bare letter key.
 *
 * Only the ones where a letter means something. Treating every <input> as
 * "typing" meant that after nudging the recency slider — a range input, where `j`
 * has no meaning whatsoever — every single-key shortcut went dead until you
 * happened to click the background. Range, checkbox and button keep the arrow and
 * space keys they need and let the rest through.
 */
const TEXTUAL = new Set(['text', 'password', 'url', 'search', 'email', 'number',
                         'tel', 'date', 'time']);

function isTextEntry(el) {
  if (!el) return false;
  if (el.isContentEditable) return true;
  const tag = el.tagName;
  if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
  return tag === 'INPUT' && TEXTUAL.has((el.type || 'text').toLowerCase());
}

document.addEventListener('keydown', (e) => {
  const typing = isTextEntry(document.activeElement);

  // Escape unwinds one layer at a time: palette, then dock, then selection.
  if (e.key === 'Escape') {
    if (palette.isOpen) return palette.close();
    if (dock.classList.contains('open')) return closeDock();
    if (orbit.selected) { orbit.deselect(); return; }
    return;
  }

  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    return palette.toggle();
  }

  if (typing) return;

  switch (e.key) {
    case '/': e.preventDefault(); palette.open(); break;
    case '>': e.preventDefault(); palette.open('>'); break;
    case '#': e.preventDefault(); palette.open('#'); break;
    case '@': e.preventDefault(); palette.open('@'); break;
    case 'a': case 'A': openTab('ask'); askView.focus(); break;
    case 'g': case 'G': openTab('gauntlet'); break;
    case ',': openTab('settings'); break;
    case '0': orbit.reset(); break;
    // 1-4 select a layout. Adjacent to 0 (reset the view), which is the family
    // these belong to — everything about how the map is arranged, on one row.
    case '1': case '2': case '3': case '4': {
      const l = LAYOUTS[Number(e.key) - 1];
      if (l) setLayout(l.id);
      break;
    }
    case '+': case '=': orbit.zoom(1.25); break;
    case '-': orbit.zoom(1 / 1.25); break;
    case 'r': case 'R': guard(() => doReindex(false))(); break;
    case 'j': { const n = orbit.step(1); if (n) openDoc(n.id); break; }
    case 'k': { const n = orbit.step(-1); if (n) openDoc(n.id); break; }
    case '?': palette.open('>'); break;
    default: break;
  }
});

/* Leaving mid-stream should not silently keep the provider generating. */
window.addEventListener('beforeunload', () => {
  askView.stop();
  gauntletView.stop();
});

boot();
