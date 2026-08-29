/* Orbit renderer — the vault as concentric ARMS rings.
 *
 * Canvas2D rather than SVG/DOM: a few thousand glowing particles plus per-frame
 * rotation is trivial on a canvas and janky with DOM nodes. Layout is
 * deterministic (polar, seeded by index) so a node never moves between reloads —
 * spatial memory is the whole value of a map, and a force simulation that
 * reshuffles on every visit destroys it.
 *
 * Interaction model, and why:
 *
 *  - **Selecting freezes the drift.** The ambient rotation is what makes the map
 *    feel alive, and exactly what makes it useless the moment you want to read
 *    something. So the spin eases to zero while a note is selected and eases back
 *    when you close it. That also lets the camera centre a node and have it stay
 *    centred, which a moving target cannot.
 *  - **Hover dims everything unconnected.** A wikilink graph is only legible one
 *    neighbourhood at a time.
 *  - **Filtered-out nodes ghost rather than vanish.** Dragging the recency
 *    scrubber should show the vault's shape thinning out over time, not delete
 *    two thirds of the picture.
 *  - **The camera lerps.** Every view change is a target the render loop eases
 *    toward, so zoom, fly-to and reset are all the same one line.
 */

export const RINGS = [
  { id: 'skills',       label: 'SKILLS',       r: 0.26, width: 0.085, bands: 6, color: '#ff8a3d' },
  { id: 'memory',       label: 'MEMORY',       r: 0.50, width: 0.130, bands: 9, color: '#b06cff' },
  { id: 'routines',     label: 'ROUTINES',     r: 0.74, width: 0.105, bands: 7, color: '#ffb03d' },
  { id: 'applications', label: 'APPLICATIONS', r: 0.94, width: 0.075, bands: 5, color: '#3ec5ff' },
];

const TAU = Math.PI * 2;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
/* Frame-rate independent easing. A fixed per-frame fraction moves twice as fast
   on a 120Hz display, which is how camera motion ends up feeling different on
   different machines. */
const ease = (cur, target, rate, dt) =>
  cur + (target - cur) * (1 - Math.exp(-rate * dt));

const LABEL_BUDGET = { sparse: { near: 6, far: 18 },
                       balanced: { near: 12, far: 40 },
                       dense: { near: 26, far: 90 } };

export class Orbit {
  constructor(canvas) {
    this.cv = canvas;
    this.ctx = canvas.getContext('2d', { alpha: false });
    this.nodes = [];
    this.edges = [];
    this.center = null;
    this.index = {};
    this.adj = new Map();

    this.hidden = new Set();
    this.since = 0;
    this.pred = null;
    this.query = new Set();

    this.spin = 0;
    this.spinRate = 1;
    this.spinTarget = 1;
    this.spinScale = 1;
    this.frozen = false;

    this.hover = null;
    this.selected = null;
    this.pulse = new Map();

    this.view = { x: 0, y: 0, k: 1 };
    this.cam = { x: 0, y: 0, k: 1 };

    this.reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      || false;
    this.labelDensity = 'balanced';

    this.dpr = clamp(window.devicePixelRatio || 1, 1, 2);
    this._raf = null;
    this._t0 = performance.now();

    this.onHover = () => {};
    this.onSelect = () => {};
    this.onViewChange = () => {};

    this._bind();
    this.resize();
  }

  /* --------------------------------------------------------------- layout */

  setData(nodes, edges) {
    this.center = nodes.find((n) => n.ring === 'core') || null;
    const live = nodes.filter((n) => n !== this.center);

    const byRing = {};
    for (const n of live) (byRing[n.ring] ||= []).push(n);

    this.nodes = [];
    for (const ring of RINGS) {
      const group = (byRing[ring.id] || []).sort(
        (a, b) => a.layer.localeCompare(b.layer) || a.title.localeCompare(b.title));
      const N = group.length;
      group.forEach((n, i) => {
        // Golden-angle offset per ring keeps sparse rings from lining up into an
        // accidental radial spoke.
        const a = N ? (i / N) * TAU + ring.r * 2.399 : 0;
        this.nodes.push(Object.assign(n, {
          ring: ring.id, color: ring.color, a0: a, rr: ring.r,
          // Deterministic radial jitter so equal-count rings don't look like a
          // grid, but a node never moves between reloads.
          jitter: ((i * 2654435761) % 1000) / 1000 * 0.028 - 0.014,
          _r: 0, _x: 0, _y: 0, _on: true,
        }));
      });
      ring.count = N;
    }

    const ids = new Set(this.nodes.map((n) => n.id));
    if (this.center) ids.add(this.center.id);
    this.edges = edges.filter((e) => ids.has(e.source) && ids.has(e.target));

    this.index = Object.fromEntries(this.nodes.map((n) => [n.id, n]));
    if (this.center) this.index[this.center.id] = this.center;

    this.adj = new Map();
    for (const e of this.edges) {
      if (!this.adj.has(e.source)) this.adj.set(e.source, new Set());
      if (!this.adj.has(e.target)) this.adj.set(e.target, new Set());
      this.adj.get(e.source).add(e.target);
      this.adj.get(e.target).add(e.source);
    }

    const times = nodes.map((n) => n.mtime || 0).filter(Boolean);
    this.oldest = times.length ? Math.min(...times) : 0;
    this.newest = times.length ? Math.max(...times) : 0;
    return RINGS;
  }

  /* ---------------------------------------------------------------- state */

  configure({ reducedMotion, spin, labelDensity } = {}) {
    if (reducedMotion !== undefined) this.reducedMotion = !!reducedMotion;
    if (spin !== undefined) this.spinScale = Number(spin) || 0;
    if (labelDensity) this.labelDensity = labelDensity;
  }

  toggleRing(id) {
    if (this.hidden.has(id)) this.hidden.delete(id);
    else this.hidden.add(id);
    return !this.hidden.has(id);
  }

  soloRing(id) {
    const others = RINGS.map((r) => r.id).filter((r) => r !== id);
    const alreadySolo = others.every((r) => this.hidden.has(r))
      && !this.hidden.has(id);
    this.hidden = alreadySolo ? new Set() : new Set(others);
    return !alreadySolo;
  }

  showAllRings() { this.hidden = new Set(); }

  ringVisible(id) { return !this.hidden.has(id); }

  /** Hide anything older than `ts` (epoch seconds). 0 shows everything. */
  setSince(ts) { this.since = ts || 0; }

  /** An extra predicate, for tag and layer filters from the palette. */
  setPredicate(fn) { this.pred = typeof fn === 'function' ? fn : null; }

  /** Count of nodes currently passing every filter. */
  visibleCount() {
    return this.nodes.filter((n) => this._passes(n)).length +
      (this.center && this._passes(this.center) ? 1 : 0);
  }

  _passes(n) {
    if (this.hidden.has(n.ring)) return false;
    if (this.since && (n.mtime || 0) < this.since) return false;
    if (this.pred && !this.pred(n)) return false;
    return true;
  }

  /** Light up search results and pull the eye to them. */
  highlight(ids) {
    this.query = new Set(ids);
    this.pulse.clear();
    ids.forEach((id, i) => this.pulse.set(id, clamp(1 - i * 0.05, 0.25, 1)));
  }

  clearHighlight() { this.query = new Set(); this.pulse.clear(); }

  /* --------------------------------------------------------------- camera */

  freeze(on) {
    this.frozen = !!on;
    this.spinTarget = on ? 0 : 1;
  }

  /** Centre a node and hold it there. Freezes the drift so it stays centred. */
  focus(id, { fly = true, zoom = 1.75 } = {}) {
    const n = this.index[id];
    if (!n) return;
    this.selected = id;
    this.pulse.set(id, 1);
    if (!fly) return;
    this.freeze(true);
    // Where the node sits relative to the scene centre, at the target zoom.
    const a = n === this.center ? 0 : n.a0 + this.spin * (1 - n.rr * 0.55);
    const rad = n === this.center ? 0 : (n.rr + n.jitter) * this.unit * zoom;
    this.cam.k = zoom;
    this.cam.x = -Math.cos(a) * rad;
    this.cam.y = -Math.sin(a) * rad;
  }

  deselect() {
    this.selected = null;
    this.freeze(false);
  }

  /** Step through the selected node's neighbours, or the ring if it has none. */
  step(delta) {
    const list = this.nodes.filter((n) => this._passes(n));
    if (!list.length) return null;
    if (!this.selected) {
      const first = list[0];
      this.focus(first.id);
      return first;
    }
    const nb = [...(this.adj.get(this.selected) || [])]
      .map((id) => this.index[id]).filter((n) => n && this._passes(n));
    const pool = nb.length ? nb : list;
    const at = pool.findIndex((n) => n.id === this.selected);
    const next = pool[(at + delta + pool.length) % pool.length];
    if (next) this.focus(next.id);
    return next || null;
  }

  reset() {
    this.cam = { x: 0, y: 0, k: 1 };
    this.selected = null;
    this.freeze(false);
  }

  zoom(f) { this.cam.k = clamp(this.cam.k * f, 0.45, 5); }

  /* ------------------------------------------------------------- geometry */

  resize() {
    // Prefer the laid-out box, but never trust a canvas's own dimensions: an
    // unlaid-out canvas reports its 300x150 intrinsic default, which would put
    // the centre of the scene in the top-left corner.
    const r = this.cv.getBoundingClientRect();
    const w = Math.round(r.width) || window.innerWidth;
    const h = Math.round(r.height) || window.innerHeight;
    this.cv.width = Math.max(1, Math.round(w * this.dpr));
    this.cv.height = Math.max(1, Math.round(h * this.dpr));
    this.w = w; this.h = h;
    this.cx = w / 2; this.cy = h / 2;
    // 0.40 rather than half the short side: the outermost zone label sits above
    // its band, and at 0.435 that label clipped off the top on short viewports.
    this.unit = Math.min(w, h) * 0.40;
    return this;
  }

  _place() {
    const { view } = this;
    const neighbours = this.hover ? this.adj.get(this.hover) : null;

    for (const n of this.nodes) {
      const a = n.a0 + this.spin * (1 - n.rr * 0.55);   // inner rings drift faster
      const r = (n.rr + n.jitter) * this.unit * view.k;
      n._x = this.cx + view.x + Math.cos(a) * r;
      n._y = this.cy + view.y + Math.sin(a) * r;
      n._a = a;
      n._r = this._radius(n);
      n._on = this._passes(n);
      n._near = !this.hover || this.hover === n.id ||
        (neighbours ? neighbours.has(n.id) : false);
    }
    if (this.center) {
      this.center._x = this.cx + view.x;
      this.center._y = this.cy + view.y;
      this.center._r = 9 * view.k;
      this.center._on = this._passes(this.center);
      this.center._near = !this.hover || this.hover === this.center.id ||
        (neighbours ? neighbours.has(this.center.id) : false);
    }
  }

  _radius(n) {
    const words = n.words || 0;
    const base = 2.7 + Math.min(Math.sqrt(words) / 9, 4.4);
    const sel = this.selected === n.id ? 2.4 : 0;
    const hov = this.hover === n.id ? 1.7 : 0;
    const hit = this.query.has(n.id) ? 1.4 : 0;
    return (base + sel + hov + hit) * this.view.k;
  }

  /* ------------------------------------------------------------- the loop */

  start() {
    // Re-measure once layout and fonts have settled; the first measurement can
    // land before the stylesheet applies.
    this.resize();
    requestAnimationFrame(() => this.resize());
    window.addEventListener('load', () => this.resize(), { once: true });
    if (document.fonts?.ready) document.fonts.ready.then(() => this.resize());

    const loop = (t) => {
      const dt = Math.min((t - this._t0) / 1000, 0.05);
      this._t0 = t;

      this.spinRate = ease(this.spinRate, this.spinTarget, 3.5, dt);
      if (!this.reducedMotion) {
        this.spin += dt * 0.028 * this.spinRate * this.spinScale;
      }

      const moved = Math.abs(this.cam.x - this.view.x) > 0.05 ||
                    Math.abs(this.cam.y - this.view.y) > 0.05 ||
                    Math.abs(this.cam.k - this.view.k) > 0.001;
      if (moved) {
        const rate = this.reducedMotion ? 40 : 7;
        this.view.x = ease(this.view.x, this.cam.x, rate, dt);
        this.view.y = ease(this.view.y, this.cam.y, rate, dt);
        this.view.k = ease(this.view.k, this.cam.k, rate, dt);
        this.onViewChange(this.view);
      }

      for (const [k, v] of this.pulse) {
        const nv = v - dt * 0.2;
        if (nv <= 0) this.pulse.delete(k); else this.pulse.set(k, nv);
      }

      this.draw();
      this._raf = requestAnimationFrame(loop);
    };
    this._raf = requestAnimationFrame(loop);
  }

  stop() { if (this._raf) cancelAnimationFrame(this._raf); }

  draw() {
    const g = this.ctx;
    g.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    g.fillStyle = '#04060b';
    g.fillRect(0, 0, this.w, this.h);
    this._place();

    this._vignette(g);
    for (const ring of RINGS) this._ring(g, ring);
    this._edges(g);
    this._nodes(g);
    if (this.center) this._center(g);
    this._ringLabels(g);
  }

  _vignette(g) {
    const cx = this.cx + this.view.x, cy = this.cy + this.view.y;
    const gr = g.createRadialGradient(cx, cy, 0, cx, cy, this.unit * 1.5);
    gr.addColorStop(0, 'rgba(30,18,48,0.5)');
    gr.addColorStop(0.45, 'rgba(10,10,26,0.24)');
    gr.addColorStop(1, 'rgba(4,6,11,0)');
    g.fillStyle = gr;
    g.fillRect(0, 0, this.w, this.h);
  }

  /* A band of concentric dotted circles rather than one line. That is what makes
     the map read as a stippled sphere instead of a wireframe diagram, and it
     gives each zone visible thickness so "which ring am I looking at" is
     answerable at a glance. Dot count scales with radius so density stays even,
     and each circle drifts at a slightly different rate so the band shimmers
     instead of rotating as a rigid disc. */
  _ring(g, ring) {
    const on = !this.hidden.has(ring.id);
    const k = this.view.k;
    const cx = this.cx + this.view.x, cy = this.cy + this.view.y;
    const inner = (ring.r - ring.width / 2) * this.unit * k;
    const outer = (ring.r + ring.width / 2) * this.unit * k;
    if (outer < 6) return;

    // Offscreen bands cost real time at high zoom and contribute nothing.
    const maxR = Math.hypot(Math.max(cx, this.w - cx), Math.max(cy, this.h - cy));
    if (inner > maxR + 40) return;

    const N = ring.bands;
    g.fillStyle = ring.color;

    for (let b = 0; b < N; b++) {
      const f = N === 1 ? 0.5 : b / (N - 1);
      const rr = inner + (outer - inner) * f;
      if (rr < 3 || rr > maxR + 30) continue;

      // Brightest in the middle of the band, feathering to the edges.
      const centreness = 1 - Math.abs(f - 0.5) * 2;
      const base = (on ? 0.5 : 0.09) * (0.3 + 0.7 * centreness) *
        (this.hover ? 0.5 : 1);

      const count = Math.max(56, Math.min(Math.round(rr * 1.15), 900));
      const drift = this.spin * (1 - ring.r * 0.5) * (0.6 + 0.4 * f) + b * 0.21;
      const dot = (0.85 + 0.5 * centreness) * Math.min(k, 1.7);

      for (let i = 0; i < count; i++) {
        const a = (i / count) * TAU + drift;
        // Cheap deterministic twinkle — no RNG, so it is stable frame to frame.
        const tw = 0.55 + 0.45 * Math.sin(i * 1.7 + b * 2.3 + this.spin * 2.4);
        g.globalAlpha = base * tw;
        g.beginPath();
        g.arc(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr, dot, 0, TAU);
        g.fill();
      }
    }

    // Faint inner boundary so zones stay distinguishable when dimmed.
    g.globalAlpha = on ? 0.1 : 0.03;
    g.strokeStyle = ring.color;
    g.lineWidth = 1;
    g.beginPath(); g.arc(cx, cy, inner, 0, TAU); g.stroke();
    g.globalAlpha = 1;
  }

  _edges(g) {
    g.lineWidth = 1;
    const cx = this.cx + this.view.x, cy = this.cy + this.view.y;
    for (const e of this.edges) {
      const a = this.index[e.source], b = this.index[e.target];
      if (!a || !b || !a._on || !b._on) continue;

      const touches = this.hover === a.id || this.hover === b.id ||
                      this.selected === a.id || this.selected === b.id;
      if (this.hover && !touches) continue;   // one neighbourhood at a time

      g.globalAlpha = touches ? 0.66 : 0.1;
      g.strokeStyle = touches ? '#cbb6ff' : '#6b5a8f';
      g.lineWidth = touches ? 1.4 : 1;
      // Quadratic toward the centre: straight chords across the middle would
      // read as a scribble; inward curves imply the hub.
      const mx = (a._x + b._x) / 2, my = (a._y + b._y) / 2;
      g.beginPath();
      g.moveTo(a._x, a._y);
      g.quadraticCurveTo(mx + (cx - mx) * 0.34, my + (cy - my) * 0.34, b._x, b._y);
      g.stroke();
    }
    g.globalAlpha = 1;
    g.lineWidth = 1;
  }

  _nodes(g) {
    for (const n of this.nodes) {
      const pulse = this.pulse.get(n.id) || 0;
      const isHit = this.query.has(n.id);
      const active = this.hover === n.id || this.selected === n.id || pulse > 0;

      // Three levels of presence: filtered out (ghost), outside the hovered
      // neighbourhood (dimmed), or live.
      let alpha = 1;
      if (!n._on) alpha = 0.1;
      else if (!n._near) alpha = 0.22;

      // The soft halo is reserved for the hovered or selected node. It used to
      // fire on every pulsing search hit too, which covered the map in two dozen
      // overlapping bokeh discs and read as a rendering fault rather than as
      // emphasis. Emphasis that applies to everything is not emphasis.
      const halo = this.hover === n.id || this.selected === n.id;
      if (halo && n._on) {
        g.globalAlpha = (0.22 + pulse * 0.22) * alpha;
        g.fillStyle = n.color;
        g.beginPath();
        g.arc(n._x, n._y, n._r * 3.2, 0, TAU);
        g.fill();
      }

      g.globalAlpha = alpha;
      g.shadowColor = n.color;
      g.shadowBlur = (active ? 20 : isHit ? 14 : 9) * this.view.k;
      // Only the one node you are pointing at or have open goes white. Painting
      // every search hit white turned twenty-four dots the same colour and threw
      // away the ring hue that the whole legend depends on; a hit keeps its
      // colour and gets a ring instead.
      g.fillStyle = active ? '#ffffff' : n.color;
      g.beginPath();
      g.arc(n._x, n._y, n._r, 0, TAU);
      g.fill();
      g.shadowBlur = 0;

      if (isHit && !active) {
        g.globalAlpha = 0.85 * alpha;
        g.strokeStyle = '#ffffff';
        g.lineWidth = 1;
        g.beginPath();
        g.arc(n._x, n._y, n._r + 3 * this.view.k, 0, TAU);
        g.stroke();
      }

      if (this.selected === n.id) {
        g.globalAlpha = 0.9;
        g.strokeStyle = '#fff';
        g.lineWidth = 1.2;
        g.beginPath();
        g.arc(n._x, n._y, n._r + 4.5 * this.view.k, 0, TAU);
        g.stroke();
      }
      g.globalAlpha = 1;
    }
    this._labels(g);
  }

  /* Labels for active and notable nodes only, with real collision rejection.
   *
   * Labelling everything produced an unreadable pile on the left-hand side. The
   * palette exists for exhaustive lookup; the map only needs enough labels to
   * orient you. Candidates are sorted so active > selected > search hit > large,
   * and any label whose box overlaps one already placed is dropped rather than
   * drawn on top — a missing label is recoverable by hovering, an illegible one
   * is not. */
  _labels(g) {
    const k = this.view.k;
    const zoomed = k > 1.4;
    const size = Math.round(10.5 * Math.min(k, 1.6));
    g.font = `500 ${size}px 'Space Grotesk', ui-sans-serif, sans-serif`;
    g.textBaseline = 'middle';

    const rank = (n) => (this.hover === n.id ? 4 : this.selected === n.id ? 3
      : this.query.has(n.id) ? 2 : this.pulse.has(n.id) ? 1 : 0);

    const cand = this.nodes.filter((n) => {
      if (!n._on) return false;
      if (rank(n) > 0) return true;
      if (this.hover && !n._near) return false;
      return zoomed || (n.words || 0) > 400;
    }).sort((a, b) => rank(b) - rank(a) || (b.words || 0) - (a.words || 0));

    const placed = [];
    const h = size + 6;
    const budgets = LABEL_BUDGET[this.labelDensity] || LABEL_BUDGET.balanced;
    const budget = zoomed ? budgets.far : budgets.near;

    for (const n of cand) {
      const active = rank(n) >= 3;
      if (placed.length >= budget && !active) break;

      const right = Math.cos(n._a) >= 0;
      const t = n.title.length > 30 ? `${n.title.slice(0, 29)}…` : n.title;
      const w = g.measureText(t).width;
      const pad = n._r + 7 * k;
      const x = n._x + (right ? pad : -pad);
      const box = { x: right ? x : x - w, y: n._y - h / 2, w, h };

      if (box.x < 4 || box.x + box.w > this.w - 4) continue;
      if (box.y < 50 || box.y + box.h > this.h - 6) continue;

      const clash = placed.some((p) => !(box.x + box.w < p.x || p.x + p.w < box.x ||
                                         box.y + box.h < p.y || p.y + p.h < box.y));
      if (clash && !active) continue;
      placed.push(box);

      g.textAlign = right ? 'left' : 'right';
      g.globalAlpha = active ? 1 : (n._near ? 0.66 : 0.3);
      g.fillStyle = active ? '#ffffff' : '#a8b6c9';
      g.save();
      g.shadowColor = 'rgba(4,6,11,.98)';
      g.shadowBlur = active ? 8 : 5;
      g.fillText(t, x, n._y);
      g.restore();
    }
    g.globalAlpha = 1;
  }

  /* The kernel. Kept small: it competed with the Skills ring for attention when
     its glow was wide, and the centre should read as a dense point of origin
     rather than a sun. */
  _center(g) {
    const n = this.center, cx = n._x, cy = n._y;
    const k = this.view.k;
    const alpha = n._on ? (n._near ? 1 : 0.3) : 0.12;

    for (let i = 3; i >= 1; i--) {
      g.globalAlpha = 0.05 * i * alpha;
      g.fillStyle = '#ff8a3d';
      g.beginPath();
      g.arc(cx, cy, (7 + i * 5.5 + Math.sin(this.spin * 5 + i) * 1.2) * k, 0, TAU);
      g.fill();
    }
    g.globalAlpha = alpha;
    g.shadowColor = '#ff8a3d'; g.shadowBlur = 18 * k;
    const gr = g.createRadialGradient(cx - 2 * k, cy - 2 * k, 0.5, cx, cy, 7.5 * k);
    gr.addColorStop(0, '#fff1dd'); gr.addColorStop(0.5, '#ff9c52');
    gr.addColorStop(1, '#b4501b');
    g.fillStyle = gr;
    g.beginPath(); g.arc(cx, cy, 7 * k, 0, TAU); g.fill();
    g.shadowBlur = 0;

    if (this.selected === n.id) {
      g.globalAlpha = 0.9; g.strokeStyle = '#fff'; g.lineWidth = 1.2;
      g.beginPath(); g.arc(cx, cy, 7 * k + 5, 0, TAU); g.stroke();
    }

    g.font = `600 ${Math.round(9.5 * Math.min(k, 1.4))}px ${'ui-monospace, monospace'}`;
    g.textAlign = 'center'; g.textBaseline = 'top';
    g.save();
    g.shadowColor = 'rgba(4,6,11,.98)'; g.shadowBlur = 7;
    g.fillStyle = '#ffcf9a';
    g.fillText('AGENTS.md', cx, cy + 12 * k);
    g.restore();
    g.globalAlpha = 1;
  }

  /* Zone labels sit just outside each band's outer edge, on the vertical axis.
     Placing them on the node radius put them on top of the nodes. */
  _ringLabels(g) {
    const cx = this.cx + this.view.x, cy = this.cy + this.view.y;
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.font = "600 9.5px 'Space Grotesk', ui-sans-serif, sans-serif";
    for (const ring of RINGS) {
      const outer = (ring.r + ring.width / 2) * this.unit * this.view.k;
      if (outer < 34) continue;
      const y = cy - outer - 9 * this.view.k;
      if (y < 52 || y > this.h - 8) continue;      // clear of the topbar
      g.globalAlpha = this.hidden.has(ring.id) ? 0.2 : (this.hover ? 0.4 : 0.8);
      g.fillStyle = ring.color;
      g.save();
      g.shadowColor = 'rgba(4,6,11,.98)'; g.shadowBlur = 9;
      g.fillText(ring.label.split('').join(' '), cx, y);
      g.restore();
    }
    g.globalAlpha = 1;
  }

  /* --------------------------------------------------------------- picking */

  at(px, py) {
    let best = null, bd = Infinity;
    const all = this.center ? this.nodes.concat([this.center]) : this.nodes;
    for (const n of all) {
      if (!n._on) continue;
      const dx = n._x - px, dy = n._y - py;
      const d = dx * dx + dy * dy;
      // A generous but bounded target: small dots are hard to hit, and a hit
      // radius that scales without limit steals clicks from its neighbours.
      const rad = clamp(n._r + 6, 9, 26);
      if (d <= rad * rad && d < bd) { best = n; bd = d; }
    }
    return best;
  }

  /* ----------------------------------------------------------------- input */

  _bind() {
    const cv = this.cv;
    let drag = null;
    let pinch = null;

    const local = (e) => {
      const r = cv.getBoundingClientRect();
      return { x: e.clientX - r.left, y: e.clientY - r.top };
    };

    cv.addEventListener('pointermove', (e) => {
      const { x, y } = local(e);
      if (drag && drag.id === e.pointerId) {
        drag.moved = drag.moved || Math.abs(x - drag.x) > 4 || Math.abs(y - drag.y) > 4;
        this.cam.x = drag.vx + (x - drag.x);
        this.cam.y = drag.vy + (y - drag.y);
        // Dragging is direct manipulation: the surface must track the finger
        // exactly, not ease toward it.
        this.view.x = this.cam.x;
        this.view.y = this.cam.y;
        return;
      }
      const hit = this.at(x, y);
      const id = hit ? hit.id : null;
      if (id !== this.hover) {
        this.hover = id;
        this.onHover(hit, e.clientX, e.clientY);
      }
      cv.classList.toggle('picking', !!hit);
    });

    cv.addEventListener('pointerdown', (e) => {
      if (e.pointerType === 'touch' && pinch) return;
      cv.setPointerCapture?.(e.pointerId);
      const { x, y } = local(e);
      drag = { id: e.pointerId, x, y, vx: this.cam.x, vy: this.cam.y, moved: false };
      cv.classList.add('dragging');
    });

    const release = (e) => {
      if (!drag || drag.id !== e.pointerId) return;
      const { x, y } = local(e);
      if (!drag.moved) {
        const hit = this.at(x, y);
        if (hit) this.onSelect(hit);
        else { this.deselect(); this.onSelect(null); }
      }
      drag = null;
      cv.classList.remove('dragging');
    };
    cv.addEventListener('pointerup', release);
    cv.addEventListener('pointercancel', () => {
      drag = null; cv.classList.remove('dragging');
    });

    cv.addEventListener('pointerleave', () => {
      if (this.hover) { this.hover = null; this.onHover(null); }
    });

    cv.addEventListener('wheel', (e) => {
      e.preventDefault();
      // Zoom toward the cursor, not the scene centre: zooming to the middle
      // means you cannot get closer to anything you are actually pointing at.
      const { x, y } = local(e);
      const before = this.cam.k;
      const f = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      const after = clamp(before * f, 0.45, 5);
      const ratio = after / before;
      const ox = x - (this.cx + this.cam.x);
      const oy = y - (this.cy + this.cam.y);
      this.cam.x -= ox * (ratio - 1);
      this.cam.y -= oy * (ratio - 1);
      this.cam.k = after;
    }, { passive: false });

    cv.addEventListener('dblclick', () => this.reset());

    /* Pinch to zoom. Two-finger gestures are the only way to zoom on a phone,
       and a map you cannot zoom on a phone is a decorative background. */
    const pts = new Map();
    cv.addEventListener('pointerdown', (e) => {
      if (e.pointerType !== 'touch') return;
      pts.set(e.pointerId, local(e));
      if (pts.size === 2) {
        drag = null;
        const [a, b] = [...pts.values()];
        pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), k: this.cam.k };
      }
    });
    cv.addEventListener('pointermove', (e) => {
      if (e.pointerType !== 'touch' || !pts.has(e.pointerId)) return;
      pts.set(e.pointerId, local(e));
      if (pinch && pts.size === 2) {
        const [a, b] = [...pts.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinch.d > 0) this.cam.k = clamp(pinch.k * (d / pinch.d), 0.45, 5);
      }
    });
    const drop = (e) => {
      pts.delete(e.pointerId);
      if (pts.size < 2) pinch = null;
    };
    cv.addEventListener('pointerup', drop);
    cv.addEventListener('pointercancel', drop);

    window.addEventListener('resize', () => this.resize());

    window.matchMedia?.('(prefers-reduced-motion: reduce)')
      .addEventListener?.('change', (e) => { this.reducedMotion = e.matches; });
  }
}
