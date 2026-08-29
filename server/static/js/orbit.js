/* Orbit renderer.
 *
 * Canvas2D rather than SVG: a few thousand glowing particles plus per-frame
 * rotation is trivial on a canvas and janky with DOM nodes.
 *
 * Position pipeline, in order:
 *   layout  → (pa, pr) polar or (px, py) cartesian, in units of `unit`
 *   morph   → lerp from the position held when the layout changed
 *   spin    → orbital drift, applied only to polar layouts
 *   camera  → pan/zoom, itself eased toward a target
 *
 * Keeping those separate is what makes a layout switch a *transition* instead of
 * a redraw, and what lets the camera fly somewhere while the layout is settling.
 */

import { RINGS, RING_INDEX, TAU, apply, easeOutCubic } from './layouts.js';
export { RINGS, LAYOUTS } from './layouts.js';

const MORPH_MS = 780;

export class Orbit {
  constructor(canvas) {
    this.cv = canvas;
    this.ctx = canvas.getContext('2d');
    this.nodes = [];
    this.edges = [];
    this.center = null;
    this.index = {};
    this.hidden = new Set();

    this.layout = 'rings';
    this.morph = 1;                 // 1 = settled
    this.spin = 0;
    this.spinRate = 0.028;
    this.nodeScale = 1;
    this.showLabels = 'auto';       // auto | all | none

    this.hover = null;
    this.selected = null;
    this.focusId = null;
    this.focusSet = null;
    this.pulse = new Map();
    this.signals = [];

    this.view = { x: 0, y: 0, k: 1 };
    this.target = { x: 0, y: 0, k: 1 };

    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this._raf = null;
    this._t0 = performance.now();
    this.onHover = () => {};
    this.onSelect = () => {};
    this.onLayout = () => {};

    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    this.reduced = mq.matches;
    mq.addEventListener?.('change', (e) => { this.reduced = e.matches; });

    this._bind();
    this.resize();
  }

  /* ------------------------------------------------------------ data */

  setData(nodes, edges) {
    this.center = nodes.find((n) => n.ring === 'core') || null;
    const live = nodes.filter((n) => n !== this.center);

    for (const n of live) {
      n.color = (RINGS[RING_INDEX[n.ring]] || RINGS[1]).color;
      n.lx ??= 0; n.ly ??= 0;        // live position, tweened
      n.ax ??= 0; n.ay ??= 0;        // position at last layout change
    }
    this.nodes = live;

    const ids = new Set(live.map((n) => n.id));
    if (this.center) ids.add(this.center.id);
    this.edges = edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    this.index = Object.fromEntries(live.map((n) => [n.id, n]));
    if (this.center) this.index[this.center.id] = this.center;

    this.adj = {};
    for (const e of this.edges) {
      (this.adj[e.source] ||= []).push(e.target);
      (this.adj[e.target] ||= []).push(e.source);
    }

    this.setLayout(this.layout, { animate: false });
    return this.ringMeta;
  }

  /* Recompute targets, remembering where everything currently is so the frame
     loop can interpolate. This is the whole trick behind "sorting animates". */
  setLayout(name, { animate = true } = {}) {
    for (const n of this.nodes) { n.ax = n.lx; n.ay = n.ly; }
    this.layout = name;
    this.ringMeta = apply(name, this.nodes, this.edges);
    for (const ring of RINGS) {
      const m = this.ringMeta?.[ring.id];
      ring.count = m ? m.count : this.nodes.filter((n) => n.ring === ring.id).length;
    }
    this.morph = animate && !this.reduced ? 0 : 1;
    if (this.morph === 1) this._settle();
    this.onLayout(name);
  }

  _settle() {
    for (const n of this.nodes) { const [x, y] = this._targetOf(n); n.lx = x; n.ly = y; }
  }

  /* Target in normalised space, spin applied for polar layouts. */
  _targetOf(n) {
    if (n.polar) {
      const a = n.pa + this.spin * (1 - n.pr * 0.5);
      return [Math.cos(a) * n.pr, Math.sin(a) * n.pr];
    }
    return [n.px, n.py];
  }

  toggleRing(id) {
    this.hidden.has(id) ? this.hidden.delete(id) : this.hidden.add(id);
  }

  highlight(ids) {
    this.pulse.clear();
    ids.forEach((id, i) => this.pulse.set(id, 1 - i * 0.06));
  }

  /* -------------------------------------------------------- geometry */

  resize() {
    const r = this.cv.getBoundingClientRect();
    const w = Math.round(r.width) || window.innerWidth;
    const h = Math.round(r.height) || window.innerHeight;
    this.cv.width = Math.max(1, Math.round(w * this.dpr));
    this.cv.height = Math.max(1, Math.round(h * this.dpr));
    this.w = w; this.h = h;
    this.cx = w / 2; this.cy = h / 2;
    this.unit = Math.min(w, h) * 0.40;
    this._bakeRings();      // bands are baked at k=1, so a size change invalidates them
    if (!this._hexPat) this._bakeHex();
    return this;
  }

  _place() {
    const e = this.morph >= 1 ? 1 : easeOutCubic(this.morph);
    const U = this.unit * this.view.k;
    const ox = this.cx + this.view.x, oy = this.cy + this.view.y;

    for (const n of this.nodes) {
      const [tx, ty] = this._targetOf(n);
      n.lx = e >= 1 ? tx : n.ax + (tx - n.ax) * e;
      n.ly = e >= 1 ? ty : n.ay + (ty - n.ay) * e;
      n._x = ox + n.lx * U;
      n._y = oy + n.ly * U;
      n._r = this._radius(n);
      n._on = !this.hidden.has(n.ring);
    }
    if (this.center) {
      this.center._x = ox; this.center._y = oy;
      this.center._r = 8 * this.view.k; this.center._on = true;
    }
  }

  _radius(n) {
    const base = 2.7 + Math.min(Math.sqrt(n.words || 0) / 9, 4.4);
    const sel = this.selected === n.id ? 2.4 : 0;
    const hov = this.hover === n.id ? 1.7 : 0;
    return (base + sel + hov) * this.view.k * this.nodeScale;
  }

  /* --------------------------------------------------------- frame */

  start() {
    this.resize();
    requestAnimationFrame(() => this.resize());
    window.addEventListener('load', () => this.resize(), { once: true });
    document.fonts?.ready?.then(() => this.resize());

    const loop = (t) => {
      const dt = Math.min((t - this._t0) / 1000, 0.05);
      this._t0 = t;
      if (!this.reduced) this.spin += dt * this.spinRate;
      if (this.morph < 1) this.morph = Math.min(1, this.morph + (dt * 1000) / MORPH_MS);
      this._easeCam(dt);
      if (this.signals.length) {
        for (const s of this.signals) s.t += dt * s.speed;
        this.signals = this.signals.filter((s) => s.t < 1);
      }
      for (const [k, v] of this.pulse) {
        const nv = v - dt * 0.22;
        nv <= 0 ? this.pulse.delete(k) : this.pulse.set(k, nv);
      }
      this.draw();
      this._raf = requestAnimationFrame(loop);
    };
    this._raf = requestAnimationFrame(loop);
  }

  stop() { if (this._raf) cancelAnimationFrame(this._raf); }

  _easeCam(dt) {
    if (this.reduced) { Object.assign(this.view, this.target); return; }
    const f = 1 - Math.exp(-dt * 7.5);
    this.view.x += (this.target.x - this.view.x) * f;
    this.view.y += (this.target.y - this.view.y) * f;
    this.view.k += (this.target.k - this.view.k) * f;
  }

  /* ---------------------------------------------------------- draw */

  draw() {
    const g = this.ctx;
    g.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    g.clearRect(0, 0, this.w, this.h);
    this._place();

    this._hexField(g);
    this._vignette(g);
    if (this.layout === 'rings') for (const ring of RINGS) this._ring(g, ring);
    else this._guide(g);
    this._edges(g);
    this._nodes(g);
    if (this.center) this._center(g);
    if (this.layout === 'rings') this._ringLabels(g);
  }

  /* Faint hex lattice, as a tiled pattern.
   *
   * It gives the pan gesture something to move against — panning an empty void
   * feels like nothing is happening — but drawn as a live path it was the single
   * most expensive thing on screen: ~1,400 line segments stroked every frame,
   * and the reason idle sat at 33fps while a zoomed-in view (fewer, larger
   * cells) hit 60. Baked into a repeating tile it is one `fillRect`.
   *
   * The tile is built at a fixed cell size and scaled by the pattern transform,
   * so zoom costs nothing extra. */
  _bakeHex() {
    const s = 34;                            // cell radius at k=1
    const w = Math.round(s * 3), h = Math.round(s * Math.sqrt(3));
    const cv = document.createElement('canvas');
    cv.width = w; cv.height = h;
    const g = cv.getContext('2d');
    g.strokeStyle = '#131b29';
    g.lineWidth = 1;
    g.beginPath();
    // Two offset cells per tile makes the seams line up on repeat.
    for (const [cx, cy] of [[0, 0], [w / 2, h / 2], [w, 0], [0, h], [w, h]]) {
      for (let i = 0; i < 6; i++) {
        const a1 = (i / 6) * TAU, a2 = ((i + 1) / 6) * TAU;
        g.moveTo(cx + Math.cos(a1) * s, cy + Math.sin(a1) * s);
        g.lineTo(cx + Math.cos(a2) * s, cy + Math.sin(a2) * s);
      }
    }
    g.stroke();
    this._hexTile = cv;
    this._hexPat = this.ctx.createPattern(cv, 'repeat');
  }

  _hexField(g) {
    if (!this._hexPat) return;
    const k = this.view.k;
    if (k < 0.55) return;
    g.save();
    g.globalAlpha = 0.55;
    // Parallax: the lattice drifts at a fraction of the camera so it reads as a
    // deeper plane than the graph.
    g.translate(this.view.x * 0.35, this.view.y * 0.35);
    g.scale(k, k);
    g.fillStyle = this._hexPat;
    const m = 200;
    g.fillRect(-m / k - this.view.x * 0.35 / k, -m / k - this.view.y * 0.35 / k,
               (this.w + m * 2) / k, (this.h + m * 2) / k);
    g.restore();
    g.globalAlpha = 1;
  }

  _vignette(g) {
    const cx = this.cx + this.view.x, cy = this.cy + this.view.y;
    const gr = g.createRadialGradient(cx, cy, 0, cx, cy, this.unit * 1.5);
    gr.addColorStop(0, 'rgba(34,20,54,0.62)');
    gr.addColorStop(0.45, 'rgba(10,10,26,0.3)');
    gr.addColorStop(1, 'rgba(4,6,11,0)');
    g.fillStyle = gr;
    g.fillRect(0, 0, this.w, this.h);
  }

  /* A single reference circle for the non-ring layouts, so the view still has a
     horizon and the zoom level stays legible. */
  _guide(g) {
    const cx = this.cx + this.view.x, cy = this.cy + this.view.y;
    g.globalAlpha = 0.16;
    g.strokeStyle = '#2a3547';
    g.setLineDash([2, 6]);
    g.beginPath();
    g.arc(cx, cy, this.unit * this.view.k, 0, TAU);
    g.stroke();
    g.setLineDash([]);
    g.globalAlpha = 1;
  }

  /* Bake each zone's stipple field to its own offscreen canvas, once.
   *
   * Drawn live this was ~15,000 arcs per frame — two per dot, for the halo and
   * the core — and measured **21 fps**. Baked, it is four `drawImage` calls with
   * a rotation, and the per-dot cost is paid once at load and on resize.
   *
   * Additive compositing ('lighter') is what makes the dots read as light rather
   * than as paint: overlaps accumulate into bloom, which is far cheaper than
   * shadowBlur and looks closer to real emission. The wide faint halo behind a
   * tight bright core is the same trick a lens does.
   *
   * What is lost by baking: per-dot twinkle. It is replaced by a slow per-zone
   * brightness oscillation, which is honest ambient motion rather than a
   * simulation of scintillation nobody was looking at. */
  _bakeRings() {
    this._baked = {};
    const U = this.unit;                     // bake at k=1; blit scales
    for (const ring of RINGS) {
      const outer = (ring.r + ring.width / 2) * U;
      const pad = 12;
      const size = Math.ceil((outer + pad) * 2);
      if (size < 8 || size > 4096) continue;

      const cv = document.createElement('canvas');
      cv.width = size; cv.height = size;
      const g = cv.getContext('2d');
      const c = size / 2;

      g.globalCompositeOperation = 'lighter';

      const inner = (ring.r - ring.width / 2) * U;
      const gr = g.createRadialGradient(c, c, Math.max(inner * 0.8, 0), c, c, outer * 1.06);
      gr.addColorStop(0, 'rgba(0,0,0,0)');
      gr.addColorStop(0.55, this._rgba(ring.glow, 0.055));
      gr.addColorStop(1, 'rgba(0,0,0,0)');
      g.fillStyle = gr;
      g.beginPath(); g.arc(c, c, outer * 1.06, 0, TAU); g.fill();

      const N = ring.bands;
      for (let b = 0; b < N; b++) {
        const f = N === 1 ? 0.5 : b / (N - 1);
        const rr = inner + (outer - inner) * f;
        if (rr < 3) continue;
        const centreness = 1 - Math.abs(f - 0.5) * 2;
        const base = 0.58 * (0.22 + 0.78 * centreness);
        const count = Math.max(90, Math.round(rr * 2.1));
        const phase = b * 0.21;
        const core = 0.9 + 0.6 * centreness;

        for (let i = 0; i < count; i++) {
          const a = (i / count) * TAU + phase;
          // Aperiodic jitter. A sine here beat against the dot spacing and the
          // band rendered as visible dashes rather than an even stipple.
          const tw = 0.40 + 0.60 * this._noise(i * 7919 + b * 104729);
          const x = c + Math.cos(a) * rr, y = c + Math.sin(a) * rr;
          g.globalAlpha = base * tw * 0.22;
          g.fillStyle = ring.glow;
          g.beginPath(); g.arc(x, y, core * 3.0, 0, TAU); g.fill();
          g.globalAlpha = base * tw;
          g.fillStyle = ring.color;
          g.beginPath(); g.arc(x, y, core, 0, TAU); g.fill();
        }
      }
      this._baked[ring.id] = cv;
    }
  }

  _ring(g, ring) {
    const img = this._baked?.[ring.id];
    if (!img) return;
    const on = !this.hidden.has(ring.id);
    const k = this.view.k;
    const cx = this.cx + this.view.x, cy = this.cy + this.view.y;
    if ((ring.r + ring.width / 2) * this.unit * k < 6) return;

    // Slow zone-level breathing stands in for the baked-out per-dot twinkle.
    const breathe = 0.9 + 0.1 * Math.sin(this.spin * 2.1 + RING_INDEX[ring.id]);

    // Plain source-over, NOT 'lighter'. The additive accumulation that creates
    // the bloom happens between dots *inside* the sprite at bake time; it is
    // already in the pixels. Compositing the finished sprite additively bought
    // nothing visually and cost every pixel of a ~500px square per zone per
    // frame — 33fps with it, 60 without.
    g.globalAlpha = (on ? 1 : 0.12) * breathe;
    g.save();
    g.translate(cx, cy);
    g.rotate(this.spin * (1 - ring.r * 0.5));
    g.scale(k, k);
    g.drawImage(img, -img.width / 2, -img.height / 2);
    g.restore();
    g.globalAlpha = 1;
  }

  /* Deterministic 0..1 hash. Same field every reload, no Math.random. */
  _noise(n) {
    let x = (n ^ 0x9e3779b9) >>> 0;
    x = Math.imul(x ^ (x >>> 15), 0x85ebca6b) >>> 0;
    x = Math.imul(x ^ (x >>> 13), 0xc2b2ae35) >>> 0;
    return ((x ^ (x >>> 16)) >>> 0) / 4294967295;
  }

  _rgba(hex, a) {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }

  _ctrl(a, b) {
    const mx = (a._x + b._x) / 2, my = (a._y + b._y) / 2;
    const cx = this.cx + this.view.x, cy = this.cy + this.view.y;
    const bend = this.layout === 'rings' ? 0.34 : 0.12;
    return [mx + (cx - mx) * bend, my + (cy - my) * bend];
  }

  _edges(g) {
    for (const e of this.edges) {
      const a = this.index[e.source], b = this.index[e.target];
      if (!a || !b || !a._on || !b._on) continue;
      const inFocus = this._lit(a.id) && this._lit(b.id);
      const touched = this.hover === a.id || this.hover === b.id ||
                      this.focusId === a.id || this.focusId === b.id;
      if (!inFocus) { g.globalAlpha = 0.03; g.strokeStyle = '#4a4060'; g.lineWidth = 1; }
      else if (touched) { g.globalAlpha = 0.78; g.strokeStyle = '#ffb98a'; g.lineWidth = 1.5; }
      else { g.globalAlpha = this.focusSet ? 0.3 : 0.1; g.strokeStyle = '#6b5a8f'; g.lineWidth = 1; }
      const [qx, qy] = this._ctrl(a, b);
      g.beginPath();
      g.moveTo(a._x, a._y);
      g.quadraticCurveTo(qx, qy, b._x, b._y);
      g.stroke();
    }
    g.globalAlpha = 1; g.lineWidth = 1;
    this._signals(g);
  }

  _signals(g) {
    for (const s of this.signals) {
      const a = this.index[s.from], b = this.index[s.to];
      if (!a || !b || !a._on || !b._on) continue;
      const [qx, qy] = this._ctrl(a, b);
      const t = s.t, u = 1 - t;
      const x = u * u * a._x + 2 * u * t * qx + t * t * b._x;
      const y = u * u * a._y + 2 * u * t * qy + t * t * b._y;
      const fade = Math.sin(Math.PI * t);
      g.globalAlpha = 0.95 * fade;
      g.fillStyle = '#ffe9d6';
      g.shadowColor = '#ff9c52';
      g.shadowBlur = 14 * this.view.k;
      g.beginPath();
      g.arc(x, y, 2.2 * this.view.k, 0, TAU);
      g.fill();
      g.shadowBlur = 0;
    }
    g.globalAlpha = 1;
  }

  /* Glyph per zone. Shape carries the category so the map still reads in
     greyscale and for colourblind users — colour is never the only signal. */
  _glyph(g, n, r, active) {
    const x = n._x, y = n._y;
    if (n.ring === 'skills') {                     // hexagon
      g.beginPath();
      for (let i = 0; i < 6; i++) {
        const a = (i / 6) * TAU - Math.PI / 2;
        const px = x + Math.cos(a) * r * 1.28, py = y + Math.sin(a) * r * 1.28;
        i ? g.lineTo(px, py) : g.moveTo(px, py);
      }
      g.closePath(); g.fill();
    } else if (n.ring === 'applications') {        // diamond
      g.beginPath();
      g.moveTo(x, y - r * 1.4); g.lineTo(x + r * 1.15, y);
      g.lineTo(x, y + r * 1.4); g.lineTo(x - r * 1.15, y);
      g.closePath(); g.fill();
    } else if (active && n.ring === 'memory') {     // four-point sparkle
      const R = r * 2.5, w = r * 0.42;
      g.beginPath();
      g.moveTo(x, y - R); g.lineTo(x + w, y - w); g.lineTo(x + R, y);
      g.lineTo(x + w, y + w); g.lineTo(x, y + R); g.lineTo(x - w, y + w);
      g.lineTo(x - R, y); g.lineTo(x - w, y - w);
      g.closePath(); g.fill();
    } else {
      g.beginPath(); g.arc(x, y, r, 0, TAU); g.fill();
    }
  }

  _nodes(g) {
    for (const n of this.nodes) {
      const pulse = this.pulse.get(n.id) || 0;
      const active = this.hover === n.id || this.selected === n.id || pulse > 0;
      const outside = !this._lit(n.id);
      const alpha = !n._on ? 0.18 : outside ? 0.14 : 1;

      if (active && n._on && !outside) {
        g.globalAlpha = 0.26 + pulse * 0.4;
        g.fillStyle = n.color;
        g.beginPath();
        g.arc(n._x, n._y, n._r * (3.4 + pulse * 2.4), 0, TAU);
        g.fill();
      }

      // Punch a dark disc first. Without it a node sitting on a lit band is
      // invisible — the band and the node are the same brightness.
      if (n._on && !outside) {
        g.globalAlpha = 0.72;
        g.fillStyle = '#04060b';
        g.beginPath();
        g.arc(n._x, n._y, n._r * 2.15 + 1.5, 0, TAU);
        g.fill();
      }

      g.globalAlpha = alpha;
      g.shadowColor = n.color;
      g.shadowBlur = (active ? 22 : 11) * this.view.k;
      g.fillStyle = active ? '#ffffff' : n.color;
      this._glyph(g, n, n._r, active);
      g.shadowBlur = 0;

      if (this.selected === n.id) {
        g.globalAlpha = 0.95;
        g.strokeStyle = '#fff';
        g.lineWidth = 1.2;
        g.beginPath();
        g.arc(n._x, n._y, n._r + 5.5 * this.view.k, 0, TAU);
        g.stroke();
      }
      g.globalAlpha = 1;
    }
    this._labels(g);
  }

  _labels(g) {
    if (this.showLabels === 'none') return;
    const k = this.view.k;
    const all = this.showLabels === 'all';
    const zoomed = k > 1.4;
    const size = Math.round(10.5 * Math.min(k, 1.6));
    g.font = `500 ${size}px ui-sans-serif,-apple-system,Segoe UI,sans-serif`;
    g.textBaseline = 'middle';

    const cand = this.nodes.filter((n) => {
      if (!n._on) return false;
      if (this.hover === n.id || this.selected === n.id) return true;
      if (this.pulse.has(n.id)) return true;
      if (this.focusSet) return this.focusSet.has(n.id);
      return all || zoomed || (n.words || 0) > 400;
    }).sort((a, b) => {
      const rank = (n) => (this.hover === n.id ? 3 : this.selected === n.id ? 2
        : this.pulse.has(n.id) ? 1 : 0);
      return rank(b) - rank(a) || (b.words || 0) - (a.words || 0);
    });

    const placed = [];
    const h = size + 6;
    const budget = all ? 200 : zoomed ? 40 : 12;
    for (const n of cand) {
      const active = this.hover === n.id || this.selected === n.id;
      if (placed.length >= budget && !active) break;
      const cxx = this.cx + this.view.x;
      const right = n._x >= cxx;
      const t = n.title.length > 30 ? n.title.slice(0, 29) + '…' : n.title;
      const w = g.measureText(t).width;
      const pad = n._r + 7 * k;
      const x = n._x + (right ? pad : -pad);
      const box = { x: right ? x : x - w, y: n._y - h / 2, w, h };

      if (box.x < 6 || box.x + box.w > this.w - 6) continue;
      if (box.y < 54 || box.y + box.h > this.h - 8) continue;
      if (box.x < 210 && box.y + box.h > this.h - 150 && !active) continue;

      const gap = 3;
      const clash = placed.some((p) =>
        !(box.x + box.w + gap < p.x || p.x + p.w + gap < box.x ||
          box.y + box.h + gap < p.y || p.y + p.h + gap < box.y));
      if (clash && !active) continue;
      const onNode = this.nodes.some((m) => m !== n && m._on &&
        m._x > box.x - 3 && m._x < box.x + box.w + 3 &&
        m._y > box.y - 2 && m._y < box.y + box.h + 2);
      if (onNode && !active) continue;
      placed.push(box);

      // Solid backing, not just a text shadow. A shadow is not enough contrast
      // over a bright stipple band, and this text has to clear 4.5:1.
      g.globalAlpha = 0.82;
      g.fillStyle = '#04060b';
      g.beginPath();
      g.roundRect?.(box.x - 4, box.y + 1, box.w + 8, box.h - 2, 4);
      if (g.roundRect) g.fill();
      else g.fillRect(box.x - 4, box.y + 1, box.w + 8, box.h - 2);

      g.textAlign = right ? 'left' : 'right';
      g.globalAlpha = active ? 1 : 0.86;
      g.fillStyle = active ? '#ffffff' : '#b6c2d2';
      g.fillText(t, x, n._y);
    }
    g.globalAlpha = 1;
  }

  /* The kernel: a reactor, not a sun. Wide glow competed with the Skills ring. */
  _center(g) {
    const n = this.center, cx = n._x, cy = n._y, k = this.view.k;
    for (let i = 3; i >= 1; i--) {
      g.globalAlpha = 0.05 * i;
      g.fillStyle = '#ff8a3d';
      g.beginPath();
      g.arc(cx, cy, (8 + i * 6 + Math.sin(this.spin * 5 + i) * 1.2) * k, 0, TAU);
      g.fill();
    }
    g.globalAlpha = 0.5;
    g.strokeStyle = '#ff8a3d';
    g.lineWidth = 1;
    g.beginPath(); g.arc(cx, cy, 15 * k, 0, TAU); g.stroke();
    g.globalAlpha = 1;

    g.shadowColor = '#ff8a3d'; g.shadowBlur = 20 * k;
    g.fillStyle = '#ff9c52';
    g.beginPath();
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * TAU - Math.PI / 2;
      const px = cx + Math.cos(a) * 8.5 * k, py = cy + Math.sin(a) * 8.5 * k;
      i ? g.lineTo(px, py) : g.moveTo(px, py);
    }
    g.closePath(); g.fill();
    g.shadowBlur = 0;

    g.font = `600 ${Math.round(9.5 * Math.min(k, 1.4))}px ui-monospace,monospace`;
    g.textAlign = 'center'; g.textBaseline = 'top';
    g.save();
    g.shadowColor = 'rgba(4,6,11,.98)'; g.shadowBlur = 7;
    g.fillStyle = '#ffcf9a';
    g.fillText('AGENTS.md', cx, cy + 18 * k);
    g.restore();
  }

  _ringLabels(g) {
    const cx = this.cx + this.view.x, cy = this.cy + this.view.y;
    const k = this.view.k;
    g.textAlign = 'center'; g.textBaseline = 'middle';

    // Zoomed in far enough that one zone fills the view? Name it big, centred —
    // the reference behaviour, and it answers "where am I" during a deep zoom.
    if (k > 2.1) {
      const near = RINGS.reduce((best, r) => {
        const d = Math.abs(r.r * this.unit * k - Math.hypot(this.view.x, this.view.y));
        return d < best.d ? { r, d } : best;
      }, { r: null, d: 1e9 }).r;
      if (near && !this.hidden.has(near.id)) {
        g.globalAlpha = 0.16;
        g.fillStyle = near.color;
        g.font = `700 ${Math.round(Math.min(64, 22 * k))}px ui-sans-serif,-apple-system,sans-serif`;
        g.fillText(near.label, this.cx, this.cy);
        g.globalAlpha = 1;
      }
    }

    g.font = '600 9.5px ui-sans-serif,-apple-system,Segoe UI,sans-serif';
    for (const ring of RINGS) {
      const outer = (ring.r + ring.width / 2) * this.unit * k;
      if (outer < 34) continue;
      const y = cy - outer - 17 * k;   // sit in the dark gap, not on the band
      if (y < 44 || y > this.h - 8) continue;
      g.globalAlpha = this.hidden.has(ring.id) ? 0.2 : 0.8;
      g.fillStyle = ring.color;
      g.save();
      g.shadowColor = 'rgba(4,6,11,.98)'; g.shadowBlur = 9;
      g.fillText(ring.label.split('').join(' '), cx, y);
      g.restore();
    }
    g.globalAlpha = 1;
  }

  /* -------------------------------------------------------- focus */

  neighbourhood(id) {
    return new Set([id, ...(this.adj[id] || [])]);
  }

  focus(id, { move = true } = {}) {
    const n = this.index[id];
    if (!n) return;
    this.selected = id;
    this.focusId = id;
    this.focusSet = this.neighbourhood(id);
    this.pulse.set(id, 1);
    if (!this.reduced) {
      for (const other of this.adj[id] || []) {
        this.signals.push({ from: id, to: other, t: 0, speed: 1.5 + Math.random() * 0.6 });
      }
    }
    if (move && n !== this.center) this.flyTo(id, { zoom: Math.max(this.target.k, 1.55) });
  }

  /* Ease the camera onto a node. Offset left of centre because the doc panel
     occupies the right third — centring it exactly would hide it. */
  flyTo(id, { zoom } = {}) {
    const n = this.index[id];
    if (!n || n === this.center) { this.reset(); return; }
    const k = zoom || Math.max(this.target.k, 1.9);
    this.target.k = k;
    this.target.x = -n.lx * this.unit * k - this.w * 0.14;
    this.target.y = -n.ly * this.unit * k;
  }

  clearFocus() { this.focusId = null; this.focusSet = null; this.selected = null; }

  ignite(id) {
    if (!this.index[id]) return;
    this.pulse.set(id, 1);
    this.focusSet = this.neighbourhood(id);
    this.focusId = id;
  }

  _lit(id) { return !this.focusSet || this.focusSet.has(id); }

  /* --------------------------------------------------------- input */

  at(px, py) {
    let best = null, bd = 1e9;
    const all = this.center ? this.nodes.concat([this.center]) : this.nodes;
    for (const n of all) {
      if (!n._on) continue;
      const dx = n._x - px, dy = n._y - py, d = dx * dx + dy * dy;
      const rad = Math.max(n._r + 6, 10);
      if (d < rad * rad && d < bd) { best = n; bd = d; }
    }
    return best;
  }

  _bind() {
    const cv = this.cv;
    let drag = null;

    cv.addEventListener('mousemove', (e) => {
      const r = cv.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      if (drag) {
        this.target.x = drag.vx + (x - drag.x);
        this.target.y = drag.vy + (y - drag.y);
        this.view.x = this.target.x; this.view.y = this.target.y;
        return;
      }
      const hit = this.at(x, y);
      const id = hit ? hit.id : null;
      if (id !== this.hover) {
        this.hover = id;
        this.onHover(hit, e.clientX, e.clientY);
      }
      cv.style.cursor = hit ? 'pointer' : 'grab';
    });

    cv.addEventListener('mousedown', (e) => {
      const r = cv.getBoundingClientRect();
      drag = { x: e.clientX - r.left, y: e.clientY - r.top,
               vx: this.target.x, vy: this.target.y };
      cv.classList.add('dragging');
    });

    window.addEventListener('mouseup', (e) => {
      if (drag) {
        const r = cv.getBoundingClientRect();
        const moved = Math.abs(e.clientX - r.left - drag.x) > 4 ||
                      Math.abs(e.clientY - r.top - drag.y) > 4;
        if (!moved) {
          const hit = this.at(e.clientX - r.left, e.clientY - r.top);
          if (hit) { this.selected = hit.id; this.onSelect(hit); }
        }
      }
      drag = null;
      cv.classList.remove('dragging');
    });

    cv.addEventListener('wheel', (e) => {
      e.preventDefault();
      const f = e.deltaY < 0 ? 1.11 : 1 / 1.11;
      this.target.k = Math.max(0.45, Math.min(5, this.target.k * f));
      this.view.k = this.target.k;
    }, { passive: false });

    cv.addEventListener('dblclick', () => this.reset());
    window.addEventListener('resize', () => this.resize());
  }

  reset() {
    this.target = { x: 0, y: 0, k: 1 };
    this.clearFocus();
    this.signals.length = 0;
  }

  zoom(f) { this.target.k = Math.max(0.45, Math.min(5, this.target.k * f)); }
}
