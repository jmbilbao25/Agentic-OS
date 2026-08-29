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
  { id: 'skills',       label: 'SKILLS',       r: 0.26, width: 0.085, bands: 6,  color: '#ff8a3d' },
  { id: 'memory',       label: 'MEMORY',       r: 0.50, width: 0.130, bands: 9,  color: '#b06cff' },
  { id: 'routines',     label: 'ROUTINES',     r: 0.74, width: 0.105, bands: 7,  color: '#ffb03d' },
  { id: 'applications', label: 'APPLICATIONS', r: 0.94, width: 0.075, bands: 5,  color: '#3ec5ff' },
];
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
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this._raf = null;
    this._t0 = performance.now();
    this.onHover = () => {};
    this.onSelect = () => {};
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
      group.forEach((n, i) => {
        // Golden-angle offset per ring keeps sparse rings from lining up into
        // an accidental radial spoke.
        const a = N ? (i / N) * TAU + ring.r * 2.399 : 0;
        this.nodes.push(Object.assign(n, {
          ring: ring.id, color: ring.color, a0: a, rr: ring.r,
          // slight radial jitter so equal-count rings don't look like a grid
          jitter: ((i * 2654435761) % 1000) / 1000 * 0.028 - 0.014,
          _r: 0, _x: 0, _y: 0,
        }));
      });
      ring.count = N;
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
      this.spin += dt * 0.028;                 // slow, ambient
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

  _edges(g) {
    g.lineWidth = 1;
    for (const e of this.edges) {
      const a = this.index[e.source], b = this.index[e.target];
      if (!a || !b || !a._on || !b._on) continue;
      const lit = this.hover === a.id || this.hover === b.id ||
                  this.selected === a.id || this.selected === b.id;
      g.globalAlpha = lit ? 0.62 : 0.1;
      g.strokeStyle = lit ? '#cbb6ff' : '#6b5a8f';
      // Quadratic toward the centre: straight chords across the middle would
      // read as a scribble; inward curves imply the hub.
      const mx = (a._x + b._x) / 2, my = (a._y + b._y) / 2;
      const cx = this.cx + this.view.x, cy = this.cy + this.view.y;
      g.beginPath();
      g.moveTo(a._x, a._y);
      g.quadraticCurveTo(mx + (cx - mx) * 0.34, my + (cy - my) * 0.34, b._x, b._y);
      g.stroke();
    }
    g.globalAlpha = 1;
  }

  _nodes(g) {
    for (const n of this.nodes) {
      const pulse = this.pulse.get(n.id) || 0;
      const active = this.hover === n.id || this.selected === n.id || pulse > 0;
      const dim = !n._on;
      const alpha = dim ? 0.2 : 1;

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

      if (box.x < 4 || box.x + box.w > this.w - 4) continue;
      if (box.y < 50 || box.y + box.h > this.h - 6) continue;

      const clash = placed.some((p) => !(box.x + box.w < p.x || p.x + p.w < box.x ||
                                         box.y + box.h < p.y || p.y + p.h < box.y));
      if (clash && !active) continue;
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

  focus(id) {
    const n = this.index[id];
    if (!n) return;
    this.selected = id;
    this.pulse.set(id, 1);
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
      this.view.k = Math.max(0.45, Math.min(4.2, this.view.k * f));
    }, { passive: false });

    cv.addEventListener('dblclick', () => this.reset());
    window.addEventListener('resize', () => this.resize());
  }

  reset() { this.view = { x: 0, y: 0, k: 1 }; }
  zoom(f) { this.view.k = Math.max(0.45, Math.min(4.2, this.view.k * f)); }
}
