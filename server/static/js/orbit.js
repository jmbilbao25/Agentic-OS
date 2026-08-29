/* Orbit renderer — the vault as concentric ARMS rings.
 *
 * Canvas2D rather than SVG/DOM: a few thousand glowing particles plus per-frame
 * rotation is trivial on a canvas and janky with DOM nodes. Layout is
 * deterministic (polar, seeded by index) so a node never moves between reloads —
 * spatial memory is the whole value of a map, and a force simulation that
 * reshuffles on every visit destroys it.
 */

/* Each ARMS zone is drawn as a *band* of many concentric dotted circles rather
 * than one line. That is what makes the map read as a stippled sphere instead of
 * a wireframe diagram — and it gives each zone visible thickness, so "which ring
 * am I looking at" is answerable at a glance. `bands` is how many circles;
 * `width` is how much radius the zone occupies; `r` is where its nodes sit. */
export const RINGS = [
  { id: 'skills',       label: 'SKILLS',       r: 0.33, width: 0.090, bands: 6, color: '#ff8a3d' },
  { id: 'memory',       label: 'MEMORY',       r: 0.60, width: 0.140, bands: 9, color: '#b06cff' },
  { id: 'routines',     label: 'ROUTINES',     r: 0.81, width: 0.090, bands: 6, color: '#ffb03d' },
  { id: 'applications', label: 'APPLICATIONS', r: 0.95, width: 0.070, bands: 5, color: '#3ec5ff' },
];

/* How many nodes a ring can hold on one orbit before it needs sub-orbits.
   Circumference grows with radius, so the inner rings crowd first — and the
   inner rings are exactly where the skills live. */
const SPACING = 0.20;   // radians of arc per node, minimum
const RING_BY_ID = Object.fromEntries(RINGS.map(r => [r.id, r]));

const TAU = Math.PI * 2;

export class Orbit {
  constructor(canvas) {
    this.cv = canvas;
    this.ctx = canvas.getContext('2d');
    this.nodes = [];
    this.edges = [];
    this.center = null;
    this.hidden = new Set();
    this.spin = 0;
    this.hover = null;
    this.selected = null;
    this.pulse = new Map();        // id -> 0..1 highlight from search
    this.view = { x: 0, y: 0, k: 1 };
    this.target = { x: 0, y: 0, k: 1 };   // camera eases toward this
    this.focusId = null;
    this.focusSet = null;          // Set of ids in the focused neighbourhood
    this.signals = [];             // travelling dots along edges
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this._raf = null;
    this._t0 = performance.now();
    this.onHover = () => {};
    this.onSelect = () => {};

    // Honour the OS-level setting rather than inventing a toggle nobody finds.
    // With reduced motion the map is fully static: no orbit drift, no signal
    // pulses, and camera moves are instant rather than eased.
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    this.reduced = mq.matches;
    mq.addEventListener?.('change', (e) => { this.reduced = e.matches; });

    this._bind();
    this.resize();
  }

  /* ------------------------------------------------------------- layout */

  setData(nodes, edges) {
    this.center = nodes.find(n => n.ring === 'core') || null;
    const live = nodes.filter(n => n !== this.center);

    // Group by ring, then order deterministically within the ring so that
    // related things (same layer, then alphabetical) sit next to each other.
    const byRing = {};
    for (const n of live) (byRing[n.ring] ||= []).push(n);

    this.nodes = [];
    for (const ring of RINGS) {
      const group = (byRing[ring.id] || []).sort(
        (a, b) => a.layer.localeCompare(b.layer) || a.title.localeCompare(b.title));
      const N = group.length;

      // Split a crowded ring into concentric sub-orbits inside its own band
      // rather than jamming everything onto one circle. With 13 skills on the
      // innermost ring, a single orbit put nodes ~0.5rad apart and every label
      // collided; two sub-orbits halve the angular density for free.
      const capacity = Math.max(4, Math.floor(TAU / SPACING * ring.r));
      const orbits = Math.max(1, Math.min(3, Math.ceil(N / capacity)));

      group.forEach((n, i) => {
        const lane = i % orbits;
        const inLane = Math.ceil((N - lane) / orbits);
        const idxInLane = Math.floor(i / orbits);
        // Lanes sit at the inner edge, middle, and outer edge of the band.
        const spread = orbits === 1 ? 0
          : (lane / (orbits - 1) - 0.5) * ring.width * 0.72;
        // Golden-angle offset per ring and per lane, so lanes interleave
        // instead of stacking into radial spokes.
        const a = inLane
          ? (idxInLane / inLane) * TAU + ring.r * 2.399 + lane * 0.618
          : 0;
        this.nodes.push(Object.assign(n, {
          ring: ring.id, color: ring.color, a0: a, rr: ring.r + spread,
          jitter: ((i * 2654435761) % 1000) / 1000 * 0.012 - 0.006,
          _r: 0, _x: 0, _y: 0,
        }));
      });
      ring.count = N;
      ring.orbits = orbits;
    }

    const ids = new Set(this.nodes.map(n => n.id));
    if (this.center) ids.add(this.center.id);
    this.edges = edges.filter(e => ids.has(e.source) && ids.has(e.target));
    this.index = Object.fromEntries(this.nodes.map(n => [n.id, n]));
    if (this.center) this.index[this.center.id] = this.center;
    return RINGS;
  }

  toggleRing(id) {
    this.hidden.has(id) ? this.hidden.delete(id) : this.hidden.add(id);
  }

  highlight(ids) {
    this.pulse.clear();
    ids.forEach((id, i) => this.pulse.set(id, 1 - i * 0.06));
  }

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
    for (const n of this.nodes) {
      const a = n.a0 + this.spin * (1 - n.rr * 0.55);   // inner rings drift faster
      const r = (n.rr + n.jitter) * this.unit * view.k;
      n._x = this.cx + view.x + Math.cos(a) * r;
      n._y = this.cy + view.y + Math.sin(a) * r;
      n._a = a;
      n._r = this._radius(n);
      n._on = !this.hidden.has(n.ring);
    }
    if (this.center) {
      this.center._x = this.cx + view.x;
      this.center._y = this.cy + view.y;
      this.center._r = 9 * view.k;
      this.center._on = true;
    }
  }

  _radius(n) {
    const words = n.words || 0;
    const base = 2.7 + Math.min(Math.sqrt(words) / 9, 4.4);
    const sel = this.selected === n.id ? 2.4 : 0;
    const hov = this.hover === n.id ? 1.7 : 0;
    return (base + sel + hov) * this.view.k;
  }

  /* ------------------------------------------------------------- drawing */

  start() {
    // Re-measure once layout and fonts have settled; the first measurement can
    // land before the stylesheet applies.
    this.resize();
    requestAnimationFrame(() => this.resize());
    window.addEventListener('load', () => this.resize(), { once: true });
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(() => this.resize());
    }
    const loop = (t) => {
      const dt = Math.min((t - this._t0) / 1000, 0.05);
      this._t0 = t;
      if (!this.reduced) this.spin += dt * 0.028;     // slow, ambient
      this._ease(dt);
      this._advance(dt);
      for (const [k, v] of this.pulse) {
        const nv = v - dt * 0.22;
        nv <= 0 ? this.pulse.delete(k) : this.pulse.set(k, nv);
      }
      this.draw();
      this._raf = requestAnimationFrame(loop);
    };
    this._raf = requestAnimationFrame(loop);
  }

  /* Exponential ease toward the camera target — frame-rate independent, so it
     behaves the same at 60Hz and 144Hz. */
  _ease(dt) {
    if (this.reduced) { Object.assign(this.view, this.target); return; }
    const f = 1 - Math.exp(-dt * 7.5);
    this.view.x += (this.target.x - this.view.x) * f;
    this.view.y += (this.target.y - this.view.y) * f;
    this.view.k += (this.target.k - this.view.k) * f;
  }

  _advance(dt) {
    if (!this.signals.length) return;
    for (const s of this.signals) s.t += dt * s.speed;
    this.signals = this.signals.filter((s) => s.t < 1);
  }

  stop() { if (this._raf) cancelAnimationFrame(this._raf); }

  draw() {
    const g = this.ctx;
    g.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    g.clearRect(0, 0, this.w, this.h);
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

  /* A band of concentric dotted circles. Dot count scales with each circle's
     radius so density stays even instead of thinning out toward the edge, and
     each circle drifts at a slightly different rate so the band shimmers rather
     than rotating as a rigid disc. */
  _ring(g, ring) {
    const on = !this.hidden.has(ring.id);
    const k = this.view.k;
    const cx = this.cx + this.view.x, cy = this.cy + this.view.y;
    const inner = (ring.r - ring.width / 2) * this.unit * k;
    const outer = (ring.r + ring.width / 2) * this.unit * k;
    if (outer < 6) return;

    const N = ring.bands;
    g.fillStyle = ring.color;

    for (let b = 0; b < N; b++) {
      const f = N === 1 ? 0.5 : b / (N - 1);
      const rr = inner + (outer - inner) * f;
      if (rr < 3) continue;

      // Brightest in the middle of the band, feathering to the edges.
      const centreness = 1 - Math.abs(f - 0.5) * 2;
      const base = (on ? 0.5 : 0.1) * (0.3 + 0.7 * centreness);

      const count = Math.max(56, Math.round(rr * 1.15));
      const drift = this.spin * (1 - ring.r * 0.5) * (0.6 + 0.4 * f)
                    + b * 0.21;         // phase offset per circle
      const dot = (0.85 + 0.5 * centreness) * Math.min(k, 1.7);

      for (let i = 0; i < count; i++) {
        const a = (i / count) * TAU + drift;
        // cheap deterministic twinkle — no RNG so it is stable frame to frame
        const tw = 0.55 + 0.45 * Math.sin(i * 1.7 + b * 2.3 + this.spin * 2.4);
        g.globalAlpha = base * tw;
        g.beginPath();
        g.arc(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr, dot, 0, TAU);
        g.fill();
      }
    }

    // faint inner boundary so zones stay distinguishable when dimmed
    g.globalAlpha = on ? 0.1 : 0.03;
    g.strokeStyle = ring.color;
    g.lineWidth = 1;
    g.beginPath(); g.arc(cx, cy, inner, 0, TAU); g.stroke();
    g.globalAlpha = 1;
  }

  /* Control point for an edge, curved toward the hub. Straight chords across the
     middle read as a scribble; inward curves imply the centre. Shared with the
     signal renderer so a pulse follows exactly the line it is drawn on. */
  _ctrl(a, b) {
    const mx = (a._x + b._x) / 2, my = (a._y + b._y) / 2;
    const cx = this.cx + this.view.x, cy = this.cy + this.view.y;
    return [mx + (cx - mx) * 0.34, my + (cy - my) * 0.34];
  }

  _edges(g) {
    g.lineWidth = 1;
    for (const e of this.edges) {
      const a = this.index[e.source], b = this.index[e.target];
      if (!a || !b || !a._on || !b._on) continue;
      const inFocus = this._lit(a.id) && this._lit(b.id);
      const touched = this.hover === a.id || this.hover === b.id ||
                      this.focusId === a.id || this.focusId === b.id;
      if (!inFocus) { g.globalAlpha = 0.03; g.strokeStyle = '#4a4060'; }
      else if (touched) { g.globalAlpha = 0.7; g.strokeStyle = '#cbb6ff'; g.lineWidth = 1.4; }
      else { g.globalAlpha = this.focusSet ? 0.3 : 0.1; g.strokeStyle = '#6b5a8f'; g.lineWidth = 1; }
      const [qx, qy] = this._ctrl(a, b);
      g.beginPath();
      g.moveTo(a._x, a._y);
      g.quadraticCurveTo(qx, qy, b._x, b._y);
      g.stroke();
    }
    g.globalAlpha = 1;
    g.lineWidth = 1;
    this._signals(g);
  }

  /* Dots travelling along links. This is the one piece of non-ambient motion:
     it fires on an explicit action and answers "what is this connected to?"
     by showing the traversal instead of asking you to trace lines. */
  _signals(g) {
    for (const s of this.signals) {
      const a = this.index[s.from], b = this.index[s.to];
      if (!a || !b || !a._on || !b._on) continue;
      const [qx, qy] = this._ctrl(a, b);
      const t = s.t, u = 1 - t;
      const x = u * u * a._x + 2 * u * t * qx + t * t * b._x;
      const y = u * u * a._y + 2 * u * t * qy + t * t * b._y;
      const fade = Math.sin(Math.PI * t);          // in and out, no pop
      g.globalAlpha = 0.9 * fade;
      g.fillStyle = '#e6d8ff';
      g.shadowColor = '#b06cff';
      g.shadowBlur = 12 * this.view.k;
      g.beginPath();
      g.arc(x, y, 2.1 * this.view.k, 0, TAU);
      g.fill();
      g.shadowBlur = 0;
    }
    g.globalAlpha = 1;
  }

  _nodes(g) {
    for (const n of this.nodes) {
      const pulse = this.pulse.get(n.id) || 0;
      const active = this.hover === n.id || this.selected === n.id || pulse > 0;
      const outside = !this._lit(n.id);
      const dim = !n._on || outside;
      const alpha = !n._on ? 0.2 : outside ? 0.16 : 1;

      if (active && !dim) {
        g.globalAlpha = 0.26 + pulse * 0.4;
        g.fillStyle = n.color;
        g.beginPath();
        g.arc(n._x, n._y, n._r * (3.4 + pulse * 2.2), 0, TAU);
        g.fill();
      }

      g.globalAlpha = alpha;
      g.shadowColor = n.color;
      g.shadowBlur = (active ? 20 : 9) * this.view.k;
      g.fillStyle = active ? '#ffffff' : n.color;
      g.beginPath();
      g.arc(n._x, n._y, n._r, 0, TAU);
      g.fill();
      g.shadowBlur = 0;

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
   * orient you. Candidates are sorted so that active > selected > large, and any
   * label whose box overlaps one already placed is dropped rather than drawn on
   * top — a missing label is recoverable by hovering, an illegible one is not. */
  _labels(g) {
    const k = this.view.k;
    const zoomed = k > 1.4;
    const size = Math.round(10.5 * Math.min(k, 1.6));
    g.font = `500 ${size}px ui-sans-serif,-apple-system,Segoe UI,sans-serif`;
    g.textBaseline = 'middle';

    const cand = this.nodes.filter((n) => {
      if (!n._on) return false;
      if (this.hover === n.id || this.selected === n.id) return true;
      if (this.pulse.has(n.id)) return true;
      // In focus mode label the whole neighbourhood: that is precisely the set
      // the user asked to see, and there are few enough of them to fit.
      if (this.focusSet) return this.focusSet.has(n.id);
      return zoomed || (n.words || 0) > 400;
    }).sort((a, b) => {
      const rank = (n) => (this.hover === n.id ? 3 : this.selected === n.id ? 2
        : this.pulse.has(n.id) ? 1 : 0);
      return rank(b) - rank(a) || (b.words || 0) - (a.words || 0);
    });

    const placed = [];
    const h = size + 6;
    const budget = zoomed ? 40 : 12;      // an orientation aid, not an index
    for (const n of cand) {
      if (placed.length >= budget &&
          this.hover !== n.id && this.selected !== n.id) break;
      const active = this.hover === n.id || this.selected === n.id;
      const right = Math.cos(n._a) >= 0;
      const t = n.title.length > 30 ? n.title.slice(0, 29) + '…' : n.title;
      const w = g.measureText(t).width;
      const pad = n._r + 7 * k;
      const x = n._x + (right ? pad : -pad);
      const box = { x: right ? x : x - w, y: n._y - h / 2, w, h };

      // Keep clear of the topbar, the viewport edges, and the legend block in
      // the lower-left — a label sitting under the legend is unreadable.
      if (box.x < 6 || box.x + box.w > this.w - 6) continue;
      if (box.y < 54 || box.y + box.h > this.h - 8) continue;
      const overLegend = box.x < 210 && box.y + box.h > this.h - 150;
      if (overLegend && !active) continue;

      // Reject against other labels AND against every visible node, with a small
      // gap. Text drawn across a glowing dot is worse than no text.
      const gap = 3;
      const clash = placed.some((p) =>
        !(box.x + box.w + gap < p.x || p.x + p.w + gap < box.x ||
          box.y + box.h + gap < p.y || p.y + p.h + gap < box.y));
      if (clash && !active) continue;

      const onNode = this.nodes.some((m) =>
        m !== n && m._on &&
        m._x > box.x - 3 && m._x < box.x + box.w + 3 &&
        m._y > box.y - 2 && m._y < box.y + box.h + 2);
      if (onNode && !active) continue;

      placed.push(box);

      g.textAlign = right ? 'left' : 'right';
      g.globalAlpha = active ? 1 : 0.62;
      g.fillStyle = active ? '#ffffff' : '#9aa7ba';
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

    for (let i = 3; i >= 1; i--) {
      g.globalAlpha = 0.05 * i;
      g.fillStyle = '#ff8a3d';
      g.beginPath();
      g.arc(cx, cy, (7 + i * 5.5 + Math.sin(this.spin * 5 + i) * 1.2) * k, 0, TAU);
      g.fill();
    }
    g.globalAlpha = 1;
    g.shadowColor = '#ff8a3d'; g.shadowBlur = 18 * k;
    const gr = g.createRadialGradient(cx - 2 * k, cy - 2 * k, 0.5, cx, cy, 7.5 * k);
    gr.addColorStop(0, '#fff1dd'); gr.addColorStop(0.5, '#ff9c52');
    gr.addColorStop(1, '#b4501b');
    g.fillStyle = gr;
    g.beginPath(); g.arc(cx, cy, 7 * k, 0, TAU); g.fill();
    g.shadowBlur = 0;

    g.font = `600 ${Math.round(9.5 * Math.min(k, 1.4))}px ui-monospace,monospace`;
    g.textAlign = 'center'; g.textBaseline = 'top';
    g.save();
    g.shadowColor = 'rgba(4,6,11,.98)'; g.shadowBlur = 7;
    g.fillStyle = '#ffcf9a';
    g.fillText('AGENTS.md', cx, cy + 12 * k);
    g.restore();
  }

  /* Zone labels sit just outside each band's outer edge, on the vertical axis.
     Placing them on the node radius put them on top of the nodes. */
  _ringLabels(g) {
    const cx = this.cx + this.view.x, cy = this.cy + this.view.y;
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.font = '600 9.5px ui-sans-serif,-apple-system,Segoe UI,sans-serif';
    for (const ring of RINGS) {
      const outer = (ring.r + ring.width / 2) * this.unit * this.view.k;
      if (outer < 34) continue;
      const y = cy - outer - 9 * this.view.k;
      if (y < 52 || y > this.h - 8) continue;      // clear of the topbar
      g.globalAlpha = this.hidden.has(ring.id) ? 0.2 : 0.8;
      g.fillStyle = ring.color;
      g.save();
      g.shadowColor = 'rgba(4,6,11,.98)'; g.shadowBlur = 9;
      g.fillText(ring.label.split('').join(' '), cx, y);
      g.restore();
    }
    g.globalAlpha = 1;
  }

  /* ------------------------------------------------------------- input */

  at(px, py) {
    let best = null, bd = 15 * 15;
    const all = this.center ? this.nodes.concat([this.center]) : this.nodes;
    for (const n of all) {
      if (!n._on) continue;
      const dx = n._x - px, dy = n._y - py, d = dx * dx + dy * dy;
      const rad = Math.max(n._r + 5, 9);
      if (d < Math.max(bd, rad * rad) && d < rad * rad + 40) { best = n; bd = d; }
    }
    return best;
  }

  /* Neighbourhood of a node: itself plus everything one wikilink away. */
  neighbourhood(id) {
    const set = new Set([id]);
    for (const e of this.edges) {
      if (e.source === id) set.add(e.target);
      if (e.target === id) set.add(e.source);
    }
    return set;
  }

  /* Focus a node: dim everything outside its 1-hop neighbourhood, ease the
     camera onto it, and fire a signal down each of its links. The dimming is
     what makes a dense graph legible — without it, highlighting one node in a
     hairball communicates nothing. */
  focus(id, { move = true } = {}) {
    const n = this.index[id];
    if (!n) return;
    this.selected = id;
    this.focusId = id;
    this.focusSet = this.neighbourhood(id);
    this.pulse.set(id, 1);

    if (!this.reduced) {
      for (const e of this.edges) {
        const other = e.source === id ? e.target : e.target === id ? e.source : null;
        if (!other) continue;
        this.signals.push({ from: id, to: other, t: 0, speed: 1.5 + Math.random() * 0.6 });
      }
    }

    if (move && n !== this.center) {
      const k = Math.max(this.target.k, 1.55);
      const a = n.a0 + this.spin * (1 - n.rr * 0.55);
      const r = (n.rr + n.jitter) * this.unit * k;
      // Offset toward the left third: the doc panel occupies the right side, so
      // centring the node exactly would put it under the panel.
      this.target.k = k;
      this.target.x = -Math.cos(a) * r - this.w * 0.14;
      this.target.y = -Math.sin(a) * r;
    }
  }

  clearFocus() {
    this.focusId = null;
    this.focusSet = null;
    this.selected = null;
  }

  /* Ignite a node without moving the camera — used when hovering a citation
     chip in an answer, so the map answers "where does this claim live?". */
  ignite(id) {
    if (!this.index[id]) return;
    this.pulse.set(id, 1);
    this.focusSet = this.neighbourhood(id);
    this.focusId = id;
  }

  _lit(id) {
    return !this.focusSet || this.focusSet.has(id);
  }

  _bind() {
    const cv = this.cv;
    let drag = null;

    cv.addEventListener('mousemove', (e) => {
      const r = cv.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      if (drag) {
        this.view.x = drag.vx + (x - drag.x);
        this.view.y = drag.vy + (y - drag.y);
        return;
      }
      const hit = this.at(x, y);
      const id = hit ? hit.id : null;
      if (id !== this.hover) {
        this.hover = id;
        this.onHover(hit, e.clientX, e.clientY);
      }
      cv.style.cursor = hit ? 'pointer' : (drag ? 'grabbing' : 'grab');
    });

    cv.addEventListener('mousedown', (e) => {
      const r = cv.getBoundingClientRect();
      drag = { x: e.clientX - r.left, y: e.clientY - r.top,
               vx: this.view.x, vy: this.view.y, moved: false };
      cv.classList.add('dragging');
    });

    window.addEventListener('mouseup', (e) => {
      if (drag) {
        const r = cv.getBoundingClientRect();
        const dx = Math.abs(e.clientX - r.left - drag.x);
        const dy = Math.abs(e.clientY - r.top - drag.y);
        if (dx < 4 && dy < 4) {
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
      this.target.k = Math.max(0.45, Math.min(4.2, this.target.k * f));
      this.view.k = this.target.k;      // wheel should feel direct, not eased
    }, { passive: false });

    cv.addEventListener('dblclick', () => this.reset());
    window.addEventListener('resize', () => this.resize());
  }

  reset() {
    this.target = { x: 0, y: 0, k: 1 };
    this.clearFocus();
    this.signals.length = 0;
  }

  zoom(f) {
    this.target.k = Math.max(0.45, Math.min(4.2, this.target.k * f));
  }
}
