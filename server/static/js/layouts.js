/* Layout engine.
 *
 * A layout assigns every node a target position in NORMALISED space: units of
 * `unit`, origin at the scene centre, y down. Rendering, spin, camera and
 * tweening belong to orbit.js. Keeping that separation is what makes switching
 * layouts an animation rather than a redraw — the renderer interpolates from
 * wherever the previous layout left each node.
 *
 * Two invariants:
 *   - **Deterministic.** Same input, same output, every reload. A node that
 *     moves between visits destroys the spatial memory that makes a map useful.
 *   - **Polar when the layout spins.** `rings` returns an angle and radius so the
 *     renderer can apply orbital drift without the layout knowing about time.
 *     Every other layout is cartesian and still.
 */

export const TAU = Math.PI * 2;

export const LAYOUTS = [
  { id: 'rings',    label: 'Rings',    hint: 'ARMS zones, orbiting' },
  { id: 'rank',     label: 'Rank',     hint: 'a line, ordered by relevance' },
  { id: 'grid',     label: 'Grid',     hint: 'dense, alphabetical' },
  { id: 'timeline', label: 'Timeline', hint: 'a line, ordered by date' },
];
export const LAYOUT_IDS = LAYOUTS.map((l) => l.id);

const MIN_ARC = 0.20;          // radians per node before a ring needs sub-orbits

/* The usable region, in normalised units, as `{ x0, x1, y0, y1 }`.
 *
 * Every flat layout needs this and none of them can derive it. A circle only ever
 * needed the smaller dimension, so the ring view could hardcode a radius of 1 and
 * be right on any screen — but a horizontal line on a 1280x580 window has almost
 * three times as much room sideways as it does vertically, and the rail covers the
 * leftmost 240 pixels of it. Laying out inside a presumed square is why the first
 * version of Rank packed 36 notes into a third of the width it had. */
const FRAME = { x0: -1.12, x1: 1.12, y0: -1.06, y1: 1.06 };

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

/* Split `N` nodes into rows of at most `perRow`, evenly.
 *
 * The obvious version fills each row and leaves the remainder in the last one,
 * which for 5 nodes in rows of 4 gives a row of four and a lonely fifth hanging
 * off the left edge — enough to visibly drag the whole arrangement off centre.
 * Balancing to 3 and 2 keeps the block symmetric and the spacing uniform between
 * rows, which matters more here than a perfectly aligned column does. */
function bands(N, perRow) {
  const rows = Math.max(1, Math.ceil(N / Math.max(1, perRow)));
  const base = Math.floor(N / rows), extra = N % rows;
  return Array.from({ length: rows }, (_, r) => base + (r < extra ? 1 : 0));
}

/* How close two nodes may sit along a line before their names cannot both be
   drawn. The renderer staggers labels over several baselines, so this is well
   under a label's width; it is the point at which even staggering fails. */
const MIN_STEP = 0.055;
/* Vertical separation between rows or lanes. Capped so a two-row line does not
   split into two unrelated bands at opposite ends of the screen. */
const MAX_GAP = 0.46;

/* Stable hash so "random-looking" offsets survive a reload. */
function hash(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return ((h >>> 0) % 100000) / 100000;
}

/* ------------------------------------------------------------------- rings */

/** The ARMS view: concentric zones, each a band of sub-orbits. Polar. */
export function rings(nodes, { RINGS }) {
  const by = {};
  for (const n of nodes) (by[n.ring] ||= []).push(n);

  for (const ring of RINGS) {
    const g = (by[ring.id] || []).sort(
      (a, b) => a.layer.localeCompare(b.layer) || a.title.localeCompare(b.title));
    const N = g.length;
    // Circumference grows with radius, so inner rings crowd first — and the
    // inner rings are where the skills live.
    const capacity = Math.max(4, Math.floor((TAU / MIN_ARC) * ring.r));
    const orbits = Math.max(1, Math.min(3, Math.ceil(N / capacity)));

    g.forEach((n, i) => {
      const lane = i % orbits;
      const inLane = Math.ceil((N - lane) / orbits) || 1;
      const idx = Math.floor(i / orbits);
      const spread = orbits === 1 ? 0
        : (lane / (orbits - 1) - 0.5) * (ring.width || 0.08) * 0.72;
      n.pa = (idx / inLane) * TAU + ring.r * 2.399 + lane * 0.618;
      n.pr = (ring.nodeR ?? ring.r) + spread + (hash(n.id) - 0.5) * 0.012;
      n.polar = true;
    });
  }
}

/* -------------------------------------------------------------------- rank */

/** A horizontal line, ordered by relevance.
 *
 * This is the layout for "line them up by what I searched for". `order` is the
 * ranked id list from the last search; anything not in it keeps its relative
 * order but is pushed to the tail and dimmed by the renderer, so the answer to
 * "what matched, best first" is a left-to-right read instead of a hunt around a
 * circle.
 *
 * Wraps to multiple rows once a single row would put nodes closer together than
 * a label can survive.
 */
export function rank(nodes, { order = [], frame = FRAME, passes = null } = {}) {
  const rankOf = new Map(order.map((id, i) => [id, i]));
  /* Filtered-out nodes go to the tail, ahead of even the search order.
   *
   * The other layouts are right to leave a hole where a filtered note was — a gap
   * in a timeline says "nothing survived that week", which is information. A
   * ranked line has no such axis, so holes in it say nothing at all, and a recency
   * filter would leave the answer scattered down a line of ghosts. Here, anything
   * excluded is simply not in the running. */
  const out = (n) => (passes && !passes(n) ? 1 : 0);
  const ordered = [...nodes].sort((a, b) => {
    const oa = out(a), ob = out(b);
    if (oa !== ob) return oa - ob;
    const ra = rankOf.has(a.id) ? rankOf.get(a.id) : Infinity;
    const rb = rankOf.has(b.id) ? rankOf.get(b.id) : Infinity;
    if (ra !== rb) return ra - rb;
    // Unmatched nodes: stable, readable fallback.
    return a.layer.localeCompare(b.layer) || a.title.localeCompare(b.title);
  });

  const N = ordered.length || 1;
  const W = (frame.x1 - frame.x0) * 0.97;
  const H = frame.y1 - frame.y0;
  const mx = (frame.x0 + frame.x1) / 2;
  const my = (frame.y0 + frame.y1) / 2;

  // Fill the width available before wrapping, rather than guessing a count.
  const counts = bands(N, clamp(Math.floor(W / MIN_STEP) + 1, 4, N));
  const rows = counts.length;
  // One step for every row, taken from the widest, so spacing does not change
  // between the first row and the last.
  const widest = Math.max(...counts);
  const stepX = widest > 1 ? W / (widest - 1) : 0;
  const gapY = rows > 1 ? Math.min(MAX_GAP, (H * 0.78) / (rows - 1)) : 0;

  let i = 0;
  counts.forEach((cnt, row) => {
    for (let c = 0; c < cnt; c++, i++) {
      const n = ordered[i];
      n.px = mx + (c - (cnt - 1) / 2) * stepX;
      n.py = my + (row - (rows - 1) / 2) * gapY;
      n.polar = false;
      n.slot = i;
      n.row = row;
      n.rankIdx = rankOf.has(n.id) ? rankOf.get(n.id) : -1;
    }
  });
  return { gapY: gapY || H * 0.5, stepX: stepX || W };
}

/* -------------------------------------------------------------------- grid */

/** Dense lattice, alphabetical within zone. For scanning names, not structure. */
export function grid(nodes, { RING_INDEX = {}, frame = FRAME } = {}) {
  const ordered = [...nodes].sort((a, b) =>
    (RING_INDEX[a.ring] ?? 9) - (RING_INDEX[b.ring] ?? 9) ||
    a.layer.localeCompare(b.layer) || a.title.localeCompare(b.title));

  const N = ordered.length || 1;
  const W = (frame.x1 - frame.x0) * 0.95;
  const H = (frame.y1 - frame.y0) * 0.86;
  const mx = (frame.x0 + frame.x1) / 2;
  const my = (frame.y0 + frame.y1) / 2;

  // Column count from the frame's own proportions, so the lattice is as square
  // on screen as the window allows rather than as square in layout units.
  const cols = clamp(Math.round(Math.sqrt(N * (W / Math.max(0.05, H)))), 1, N);
  const counts = bands(N, cols);
  const rows = counts.length;
  const widest = Math.max(...counts);
  const stepX = widest > 1 ? W / (widest - 1) : 0;
  const gapY = rows > 1 ? Math.min(MAX_GAP, H / (rows - 1)) : 0;

  let i = 0;
  counts.forEach((cnt, r) => {
    for (let c = 0; c < cnt; c++, i++) {
      const n = ordered[i];
      n.px = mx + (c - (cnt - 1) / 2) * stepX;
      n.py = my + (r - (rows - 1) / 2) * gapY;
      n.polar = false;
      n.slot = i;
      n.row = r;
    }
  });
  return { gapY: gapY || H * 0.5, stepX: stepX || W };
}

/* ---------------------------------------------------------------- timeline */

/** Horizontal by mtime, oldest left. Vertically lanes by zone so a busy day
 *  does not become one unreadable stack. Pairs with the existing time scrub. */
export function timeline(nodes, { RING_INDEX = {}, frame = FRAME } = {}) {
  const times = nodes.map((n) => n.mtime || 0).filter(Boolean);
  const lo = times.length ? Math.min(...times) : 0;
  const hi = times.length ? Math.max(...times) : 0;
  // A single node — or a vault where every file shares one mtime — has no span.
  // Dividing by a fallback of 1 put t=0 for everything, which pinned the whole
  // layout to the left edge instead of centring it.
  const span = hi - lo;
  const noSpan = span <= 0;

  const W = (frame.x1 - frame.x0) * 0.94;
  const H = frame.y1 - frame.y0;
  const mx = (frame.x0 + frame.x1) / 2;
  const my = (frame.y0 + frame.y1) / 2;

  // Lane extent from the zones actually present, not from the full ring list: a
  // vault with nothing in Applications should not reserve a band for it.
  const laneOf = (n) => RING_INDEX[n.ring] ?? 0;
  const lanes = nodes.length ? nodes.map(laneOf) : [0];
  const lmin = Math.min(...lanes), lmax = Math.max(...lanes);
  const gapY = lmax > lmin ? Math.min(MAX_GAP, (H * 0.66) / (lmax - lmin)) : 0;

  const ordered = [...nodes].sort((a, b) => (a.mtime || 0) - (b.mtime || 0));

  /* Real vaults are edited in bursts, so most notes share a timestamp with
   * several others. The first version nudged each duplicate down by a fixed step,
   * which turned a day's work into a vertical spike that grew into the next lane —
   * the busiest day became the least readable part of the picture, and the lane
   * colours stopped meaning anything.
   *
   * Instead, tied nodes are collected first and then dealt out as a small block
   * centred on the lane: a burst reads as a cluster with a known centre, it never
   * escapes its own band, and once a block is taller than the band allows it
   * grows sideways into the time it actually occupies. */
  const groups = new Map();
  for (const n of ordered) {
    const t = noSpan ? 0.5 : ((n.mtime || lo) - lo) / span;
    const key = `${laneOf(n)}:${Math.round(t * 160)}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push([n, t]);
  }

  const step = gapY ? Math.min(gapY * 0.20, 0.072) : 0.072;
  const stack = Math.max(1, Math.floor((gapY ? gapY * 0.78 : H * 0.4) / step));
  /* Sideways spread is wider than the vertical step, and can be: notes sharing a
     timestamp have no true left-to-right order, so spending horizontal room on
     them costs no accuracy and buys the separation that stops a burst rendering
     as one fat blob. Distinct timestamps land in distinct buckets and never fan,
     so the axis stays honest where it carries information. */
  const fan = step * 1.6;

  for (const members of groups.values()) {
    const tall = Math.min(members.length, stack);
    const wide = Math.ceil(members.length / tall);
    members.forEach(([n, t], k) => {
      const row = k % tall;
      const col = Math.floor(k / tall);
      // Centred on the true time, not started from it: a cluster that grows only
      // rightwards drifts away from the moment it is reporting, and the last
      // cluster of the day grows straight off the edge of the frame.
      n.px = mx + (t - 0.5) * W + (col - (wide - 1) / 2) * fan;
      n.py = my + (laneOf(n) - (lmin + lmax) / 2) * gapY
             + (row - (tall - 1) / 2) * step;
      n.polar = false;
      n.row = laneOf(n) - lmin;
    });
  }
  ordered.forEach((n, i) => { n.slot = i; });
  return { gapY: gapY || H * 0.5, stepX: fan };
}

/* ------------------------------------------------------------------ apply */

/** Place `nodes` and report the spacing the renderer needs to label them. */
export function apply(name, nodes, ctx = {}) {
  switch (name) {
    case 'rank':     return rank(nodes, ctx);
    case 'grid':     return grid(nodes, ctx);
    case 'timeline': return timeline(nodes, ctx);
    default:         return rings(nodes, ctx) || { gapY: 0.2, stepX: 0.2 };
  }
}

export const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);

/* ponytail: one runnable check, no framework. `node server/static/js/layouts.js`
 * Ceiling: geometry only — it asserts nothing about how the result looks. */
export function _selfcheck() {
  // console.assert only logs in Node, so the first version of this printed OK
  // while three assertions were failing. Count and throw.
  let failures = 0;
  const ok = (cond, msg) => { if (!cond) { failures++; console.error('  FAIL ' + msg); } };

  const RINGS = [
    { id: 'skills', r: 0.30, nodeR: 0.375, width: 0.085 },
    { id: 'memory', r: 0.56, nodeR: 0.645, width: 0.115 },
    { id: 'routines', r: 0.80, nodeR: 0.862, width: 0.070 },
    { id: 'applications', r: 0.93, nodeR: 0.975, width: 0.055 },
  ];
  const RING_INDEX = Object.fromEntries(RINGS.map((r, i) => [r.id, i]));
  const mk = (count) => Array.from({ length: count }, (_, i) => ({
    id: 'n' + i, ring: RINGS[i % RINGS.length].id, layer: 'wiki',
    title: 'note ' + i, words: 100, mtime: 1700000000 + i * 3600,
  }));

  const pos = (n) => (n.polar
    ? [Math.cos(n.pa) * n.pr, Math.sin(n.pa) * n.pr] : [n.px, n.py]);

  // A wide window, a tall one, and a wide one with the rail taking the left third.
  // The rail case is the one that actually ships, and the one the first version
  // laid out straight through.
  const FRAMES = {
    wide:  { x0: -2.7, x1: 2.7, y0: -1.2, y1: 1.2 },
    tall:  { x0: -1.2, x1: 1.2, y0: -2.4, y1: 2.4 },
    railed: { x0: -1.6, x1: 2.7, y0: -1.0, y1: 1.2 },
  };

  for (const count of [1, 5, 36, 200]) {
    for (const name of LAYOUT_IDS) {
      for (const [fname, frame] of Object.entries(FRAMES)) {
        const nodes = mk(count);
        const tag = `${name}/${count}/${fname}`;
        const metrics = apply(name, nodes,
          { RINGS, RING_INDEX, frame, order: nodes.slice(0, 5).map((n) => n.id) });
        const cartesian = name !== 'rings';
        let cx = 0, cy = 0;
        for (const n of nodes) {
          const [x, y] = pos(n);
          ok(Number.isFinite(x) && Number.isFinite(y), `${tag}: non-finite position`);
          if (cartesian) {
            // Inside the frame it was given, with a small tolerance for the
            // half-step a tie-cluster or a wrapped row can add.
            ok(x >= frame.x0 - 0.12 && x <= frame.x1 + 0.12,
              `${tag}: ${n.id} escaped horizontally at ${x.toFixed(2)}`);
            ok(y >= frame.y0 - 0.12 && y <= frame.y1 + 0.12,
              `${tag}: ${n.id} escaped vertically at ${y.toFixed(2)}`);
          } else {
            ok(Math.abs(x) <= 1.3 && Math.abs(y) <= 1.3,
              `${tag}: ${n.id} escaped the unit circle at ${x},${y}`);
          }
          cx += x; cy += y;
        }
        cx /= nodes.length; cy /= nodes.length;

        if (cartesian) {
          ok(metrics && metrics.gapY > 0,
            `${tag}: no gapY reported — the renderer cannot size label stacks`);
          // Centroid near the frame's middle, not the origin's: a framed layout is
          // supposed to be off-origin when the rail pushes it right.
          const fx = (frame.x0 + frame.x1) / 2, fy = (frame.y0 + frame.y1) / 2;
          if (count >= 4) {
            ok(Math.abs(cx - fx) < 0.35,
              `${tag}: centroid x ${cx.toFixed(2)} not near frame centre ${fx}`);
            ok(Math.abs(cy - fy) < 0.35,
              `${tag}: centroid y ${cy.toFixed(2)} not near frame centre ${fy}`);
            const slots = new Set(nodes.map((n) => n.slot));
            ok(slots.size === count, `${tag}: slot not tagged uniquely`);
          }
          // The point of the frame: use it. A layout that fits 36 notes into a
          // quarter of the width it was handed is the bug this pins down.
          if (count >= 20 && name !== 'timeline') {
            const xs = nodes.map((n) => n.px);
            const used = Math.max(...xs) - Math.min(...xs);
            ok(used > (frame.x1 - frame.x0) * 0.7,
              `${tag}: used only ${used.toFixed(2)} of ${
                (frame.x1 - frame.x0).toFixed(2)} available width`);
          }
        }
      }
    }
  }

  // rank must honour the supplied order, left to right
  const nodes = mk(20);
  const order = ['n7', 'n3', 'n11'];
  rank(nodes, { order });
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  ok(byId.n7.px < byId.n3.px && byId.n3.px < byId.n11.px,
    'rank: ranked nodes are not left-to-right');
  ok(byId.n7.rankIdx === 0 && byId.n0.rankIdx === -1, 'rank: rankIdx not tagged');

  // a filter outranks the search order: excluded notes go to the tail even if the
  // query matched them
  const filt = mk(20);
  const keep = new Set(['n2', 'n5', 'n9', 'n14']);
  rank(filt, { order: ['n7', 'n2'], passes: (n) => keep.has(n.id) });
  const fid = Object.fromEntries(filt.map((n) => [n.id, n]));
  const worstKept = Math.max(...[...keep].map((id) => fid[id].px));
  const bestDropped = Math.min(...filt.filter((n) => !keep.has(n.id)).map((n) => n.px));
  ok(worstKept < bestDropped,
    'rank: a filtered-out note is sitting ahead of one that passed');
  ok(fid.n2.px < fid.n5.px, 'rank: search order lost within the kept set');

  /* The shape of this vault: everything edited on one of two days. It is also the
   * worst case for a timeline, and the one the fixed-nudge version turned into two
   * vertical spikes that overran their lanes. */
  const bursty = mk(40).map((n, i) => ({
    ...n, mtime: i < 22 ? 1700000000 : 1700864000,
  }));
  const tmetrics = timeline(bursty, { RING_INDEX, frame: FRAMES.railed });
  const laneSpan = tmetrics.gapY;
  for (const r of RINGS) {
    const inLane = bursty.filter((n) => n.ring === r.id);
    if (inLane.length < 2) continue;
    const ys = inLane.map((n) => n.py);
    const spread = Math.max(...ys) - Math.min(...ys);
    ok(spread < laneSpan,
      `timeline: ${r.id} spreads ${spread.toFixed(2)} beyond its ${
        laneSpan.toFixed(2)} lane — bursts are colliding with the next zone`);
  }

  // determinism
  const a = mk(30); rings(a, { RINGS });
  const b = mk(30); rings(b, { RINGS });
  ok(a.every((n, i) => n.pa === b[i].pa && n.pr === b[i].pr),
    'rings: not deterministic');

  // timeline must be monotonic in x, allowing for the sideways growth a tie
  // cluster uses once it is taller than its lane
  const t = mk(12); timeline(t, { RING_INDEX });
  const xs = [...t].sort((p, q) => (p.mtime || 0) - (q.mtime || 0)).map((n) => n.px);
  ok(xs.every((x, i) => i === 0 || x >= xs[i - 1] - 0.08),
    'timeline: x is not monotonic in time');

  // a flat vault (every mtime identical) must centre, not pile up on the left
  const flat = mk(6).map((n) => ({ ...n, mtime: 1700000000 }));
  timeline(flat, { RING_INDEX });
  ok(flat.every((n) => Math.abs(n.px) < 0.12),
    'timeline: a flat time span did not centre');

  if (failures) throw new Error(`layouts selfcheck: ${failures} failure(s)`);
  console.log('layouts selfcheck OK');
}

if (typeof process !== 'undefined' && process.argv?.[1]?.endsWith('layouts.js')) {
  _selfcheck();
}
