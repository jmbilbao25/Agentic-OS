/* The command palette.
 *
 * Four modes on one input, chosen by the first character:
 *
 *   (none)  find     hybrid search across the vault
 *   >       run      commands
 *   #       tag      filter by frontmatter tag
 *   @       layer    filter by vault layer
 *
 * One input rather than four buttons because the fastest interface for someone
 * who knows what they want is the one that never asks them to aim.
 *
 * Typing always paints instantly from the graph already in memory, then the
 * server's hybrid ranking replaces it when it lands. A search box that waits
 * 200ms before showing anything feels broken even when it is fast.
 */

import { get } from './api.js';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const MODES = {
  find: { key: '', label: 'find', hint: 'Search titles, text and meaning…' },
  run: { key: '>', label: 'run', hint: 'Run a command…' },
  tag: { key: '#', label: 'tag', hint: 'Filter by tag…' },
  layer: { key: '@', label: 'layer', hint: 'Filter by layer…' },
};

export class Palette {
  constructor({ onOpenDoc, onAsk, onFilter, commands, nodes }) {
    this.el = document.getElementById('palette');
    this.input = document.getElementById('pal-q');
    this.hitsEl = document.getElementById('pal-hits');
    this.modeEl = document.getElementById('pal-mode');
    this.countEl = document.getElementById('pal-count');

    this.onOpenDoc = onOpenDoc;
    this.onAsk = onAsk;
    this.onFilter = onFilter;
    this.commands = commands;      // () => [{id,label,hint,run,keys}]
    this.nodes = nodes;            // () => node[]

    this.mode = 'find';
    this.rows = [];
    this.sel = 0;
    this.timer = null;
    this.seq = 0;

    this.input.addEventListener('input', () => this.onInput());
    this.input.addEventListener('keydown', (e) => this.key(e));
    this.hitsEl.addEventListener('click', (e) => {
      const b = e.target.closest('[data-idx]');
      if (b) this.choose(Number(b.dataset.idx));
    });
    this.hitsEl.addEventListener('mousemove', (e) => {
      const b = e.target.closest('[data-idx]');
      if (!b) return;
      const i = Number(b.dataset.idx);
      if (i !== this.sel) { this.sel = i; this.paintSelection(); }
    });
  }

  get isOpen() { return this.el.classList.contains('open'); }

  open(seed = '') {
    this.el.classList.add('open');
    this.input.value = seed;
      this.input.focus();
    this.input.select();
    this.onInput();
  }

  close() {
    this.el.classList.remove('open');
    this.input.blur();
    this.onClose?.();
  }

  toggle() { this.isOpen ? this.close() : this.open(); }

  /* ------------------------------------------------------------------ input */

  parse() {
    const raw = this.input.value;
    for (const [name, m] of Object.entries(MODES)) {
      if (m.key && raw.startsWith(m.key)) {
        return { mode: name, q: raw.slice(m.key.length).trim() };
      }
    }
    return { mode: 'find', q: raw.trim() };
  }

  onInput() {
    const { mode, q } = this.parse();
    this.mode = mode;
    this.modeEl.textContent = MODES[mode].label;
    this.input.placeholder = MODES[mode].hint;

    clearTimeout(this.timer);

    if (mode === 'run') return this.paint(this.matchCommands(q), q);
    if (mode === 'tag') return this.paint(this.matchTags(q), q);
    if (mode === 'layer') return this.paint(this.matchLayers(q), q);

    this.paint(this.matchLocal(q), q);            // instant
    if (q.length >= 2) {
      const mine = ++this.seq;
      this.timer = setTimeout(() => this.remote(q, mine), 180);
    }
  }

  async remote(q, mine) {
    try {
      const r = await get(`/api/search?k=25&q=${encodeURIComponent(q)}`);
      if (mine !== this.seq) return;              // a newer keystroke won
      if (this.parse().q !== q) return;
      if (!r.hits.length) return;                 // keep the local guesses
      this.paint(r.hits.map((h) => ({
        kind: 'doc', id: h.doc_id, title: h.title, layer: h.layer,
        snip: tidy(h.text), tag: h.matched,
      })), q, r.mode);
    } catch { /* local results stand */ }
  }

  /* ---------------------------------------------------------------- matchers */

  matchLocal(q) {
    const s = q.toLowerCase();
    const all = this.nodes();
    const list = !s ? all.slice(0, 50) : all.filter((n) =>
      n.title.toLowerCase().includes(s) || n.path.toLowerCase().includes(s) ||
      (n.tags || []).some((t) => t.toLowerCase().includes(s)));
    return list.slice(0, 50).map((n) => ({
      kind: 'doc', id: n.id, title: n.title, layer: n.layer,
      snip: n.excerpt, tag: 'name',
    }));
  }

  matchCommands(q) {
    const s = q.toLowerCase();
    return this.commands()
      .filter((c) => !s || c.label.toLowerCase().includes(s) ||
                     (c.hint || '').toLowerCase().includes(s))
      .map((c) => ({ kind: 'cmd', cmd: c, title: c.label, snip: c.hint,
                     tag: c.keys || '' }));
  }

  matchTags(q) {
    const s = q.toLowerCase();
    const counts = new Map();
    for (const n of this.nodes()) {
      for (const t of n.tags || []) {
        if (!s || t.toLowerCase().includes(s)) {
          counts.set(t, (counts.get(t) || 0) + 1);
        }
      }
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([t, n]) => ({ kind: 'tag', tag: `${n} note${n === 1 ? '' : 's'}`,
                          value: t, title: `#${t}`,
                          snip: 'Show only notes carrying this tag' }));
  }

  matchLayers(q) {
    const s = q.toLowerCase();
    const counts = new Map();
    for (const n of this.nodes()) {
      if (!s || n.layer.toLowerCase().includes(s)) {
        counts.set(n.layer, (counts.get(n.layer) || 0) + 1);
      }
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1])
      .map(([l, n]) => ({ kind: 'layer', tag: `${n} note${n === 1 ? '' : 's'}`,
                          value: l, title: `@${l}`,
                          snip: 'Show only this layer' }));
  }

  /* ------------------------------------------------------------------ paint */

  paint(rows, q, srcMode) {
    this.rows = rows;
    this.sel = 0;
    this.countEl.textContent = rows.length
      ? `${srcMode ? `${srcMode} · ` : ''}${rows.length}` : '';

    if (!rows.length) {
      this.hitsEl.innerHTML = `<div class="empty">
        <svg class="i" aria-hidden="true"><use href="#i-empty"/></svg>
        <b>Nothing matches${q ? ` “${esc(q)}”` : ''}</b>
        <p>Try fewer words, or press <kbd>Shift Enter</kbd> to ask the vault
        instead of searching it.</p></div>`;
      return;
    }

    const words = q.split(/\s+/).filter((w) => w.length > 2)
      .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const hl = (s) => {
      let t = esc(s);
      for (const w of words) t = t.replace(new RegExp(`(${w})`, 'gi'), '<mark>$1</mark>');
      return t;
    };

    this.hitsEl.innerHTML = rows.map((r, i) => `
      <button class="hit${i === 0 ? ' sel' : ''}" data-idx="${i}">
        <span class="hit-top">
          <b>${hl(r.title)}</b>
          ${r.layer ? `<span class="ly">${esc(r.layer)}</span>` : ''}
          ${r.tag ? `<span class="mt">${esc(r.tag)}</span>` : ''}
        </span>
        ${r.snip ? `<span class="snip">${hl(r.snip)}</span>` : ''}
      </button>`).join('');
    this.hitsEl.scrollTop = 0;
  }

  paintSelection() {
    const els = this.hitsEl.querySelectorAll('.hit');
    els.forEach((el, i) => el.classList.toggle('sel', i === this.sel));
    els[this.sel]?.scrollIntoView({ block: 'nearest' });
  }

  move(d) {
    if (!this.rows.length) return;
    this.sel = (this.sel + d + this.rows.length) % this.rows.length;
    this.paintSelection();
  }

  choose(i) {
    const r = this.rows[i ?? this.sel];
    if (!r) return;
    if (r.kind === 'doc') { this.close(); this.onOpenDoc(r.id); }
    else if (r.kind === 'cmd') { this.close(); r.cmd.run(); }
    else if (r.kind === 'tag') { this.close(); this.onFilter({ tag: r.value }); }
    else if (r.kind === 'layer') { this.close(); this.onFilter({ layer: r.value }); }
  }

  key(e) {
    if (e.key === 'ArrowDown' || (e.key === 'n' && e.ctrlKey)) {
      e.preventDefault(); this.move(1);
    } else if (e.key === 'ArrowUp' || (e.key === 'p' && e.ctrlKey)) {
      e.preventDefault(); this.move(-1);
    } else if (e.key === 'Home' && this.rows.length) {
      e.preventDefault(); this.sel = 0; this.paintSelection();
    } else if (e.key === 'End' && this.rows.length) {
      e.preventDefault(); this.sel = this.rows.length - 1; this.paintSelection();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const { q } = this.parse();
      if (e.shiftKey && this.mode === 'find' && q) { this.close(); this.onAsk(q); }
      else this.choose();
    } else if (e.key === 'Escape') {
      e.preventDefault(); this.close();
    } else if (e.key === 'Tab') {
      // Cycle modes without reaching for the punctuation.
      e.preventDefault();
      const order = ['find', 'run', 'tag', 'layer'];
      const next = order[(order.indexOf(this.mode) + 1) % order.length];
      const { q } = this.parse();
      this.input.value = MODES[next].key + q;
      this.onInput();
    }
  }
}

/* Chunks are split mid-sentence, so a raw excerpt often opens on a word fragment
   ("x as disposable…"). Drop a leading partial word unless it looks like a real
   sentence start. */
function tidy(s) {
  const t = (s || '').trim().replace(/^\S*\s+/, (m) => (/^[A-Z(“"'[]/.test(m) ? m : ''));
  return t.slice(0, 200);
}
