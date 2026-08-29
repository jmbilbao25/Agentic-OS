/* Layout engine.
 *
 * A layout's only job is to assign every node a target position in NORMALISED
 * world space — units of `unit`, origin at the centre, y down. Rendering, spin,
 * and tweening are somebody else's problem. Keeping it that way is what makes
 * switching layouts an animation rather than a redraw: the renderer interpolates
 * between whatever the previous layout produced and whatever the new one does.
 *
 * Two hard rules:
 *  - **Deterministic.** Same input, same output, every time. A node that moves
 *    between reloads destroys the spatial memory that makes a map worth having.
 *  - **Polar where possible.** `rings` returns angle + radius so the renderer can
 *    apply orbital drift without the layout knowing anything about time.
 */

export const TAU = Math.PI * 2;

/* Zone geometry. `r` is where the nodes sit; the band is drawn around it so the
   dots and the nodes occupy the same space — in the first pass the bands sat in
   the gaps between node orbits and the map read as sparse.
   Colours are pushed brighter and more saturated than a normal UI palette
   because they are seen as thin luminous dots against near-black, where a muted
   hue disappears entirely. */
/* Zone geometry.
 *
 * Widths are deliberately narrow so there is BLACK between zones. A first pass
 * used wide bands and the four zones merged into one luminous disc that drowned
 * every node and made white labels unreadable — the gaps are what make the
 * structure legible, not the bands.
 *
 * `nodeR` offsets the node orbit off the band's bright centre line, so nodes sit
 * against darker background instead of competing with the stipple. */
export const RINGS = [
  { id: 'skills',       label: 'SKILLS',       r: 0.30, nodeR: 0.375, width: 0.085, bands: 7,  color: '#ff9a3c', glow: '#ff6a00' },
  { id: 'memory',       label: 'MEMORY',       r: 0.56, nodeR: 0.645, width: 0.115, bands: 10, color: '#c76bff', glow: '#8b2fd6' },
  { id: 'routines',     label: 'ROUTINES',     r: 0.80, nodeR: 0.862, width: 0.070, bands: 6,  color: '#ffbe45', glow: '#c98a10' },
  { id: 'applications', label: 'APPLICATIONS', r: 0.93, nodeR: 0.975, width: 0.055, bands: 5,  color: '#4fd2ff', glow: '#1a86c9' },
];

export const RING_INDEX = Object.fromEntries(RINGS.map((r, i) => [r.id, i]));

export const LAYOUTS = ['rings', 'circle', 'hex', 'force'];

const MIN_ARC = 0.20;          // radians per node before a ring needs sub-orbits

/* Stable 32-bit hash, so "random-looking" offsets survive a reload. */
function hash(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return ((h >>> 0) % 100000) / 100000;
}

function grouped(nodes) {
  const by = {};
  for (const n of nodes) (by[n.ring] ||= []).push(n);
  for (const k in by) {
    by[k].sort((a, b) => a.layer.localeCompare(b.layer) || a.title.localeCompare(b.title));
  }
  return by;
}

/* ------------------------------------------------------------------- rings */
/* The ARMS view: concentric zones, each a band of sub-orbits. Returns polar so
   the renderer can spin it. */
export function rings(nodes) {
  const by = grouped(nodes);
  const meta = {};
  for (const ring of RINGS) {
    const g = by[ring.id] || [];
    const N = g.length;
    const capacity = Math.max(4, Math.floor((TAU / MIN_ARC) * ring.r));
    const orbits = Math.max(1, Math.min(3, Math.ceil(N / capacity)));
    meta[ring.id] = { count: N, orbits };

    g.forEach((n, i) => {
      const lane = i % orbits;
      const inLane = Math.ceil((N - lane) / orbits) || 1;
      const idx = Math.floor(i / orbits);
      const spread = orbits === 1 ? 0 : (lane / (orbits - 1) - 0.5) * ring.width * 0.72;
      n.pa = (idx / inLane) * TAU + ring.r * 2.399 + lane * 0.618;
      n.pr = (ring.nodeR ?? ring.r) + spread + (hash(n.id) - 0.5) * 0.012;
      n.polar = true;
    });
  }
  return meta;
}

/* ------------------------------------------------------------------ circle */
/* Every node on one ring, ordered by zone then title. Good for "show me
   everything at once" and for reading labels — nothing is occluded. */
export function circle(nodes) {
  const ordered = [...nodes].sort((a, b) =>
    (RING_INDEX[a.ring] ?? 9) - (RING_INDEX[b.ring] ?? 9) ||
    a.layer.localeCompare(b.layer) || a.title.localeCompare(b.title));
  const N = ordered.length || 1;
  // Two concentric rings once it gets crowded, so labels stay legible.
  const lanes = N > 34 ? 2 : 1;
  ordered.forEach((n, i) => {
    const lane = i % lanes;
    const inLane = Math.ceil((N - lane) / lanes) || 1;
    const idx = Math.floor(i / lanes);
    n.pa = (idx / inLane) * TAU - Math.PI / 2;
    n.pr = 0.93 - lane * 0.16;
    n.polar = true;
  });
  return {};
}

/* --------------------------------------------------------------------- hex */
/* Hexagonal lattice, spiralling out from the centre, grouped so each zone's
   nodes stay adjacent. Dense and orderly — the layout for scanning filenames
   rather than for seeing structure. */
export function hex(nodes) {
  const ordered = [...nodes].sort((a, b) =>
    (RING_INDEX[a.ring] ?? 9) - (RING_INDEX[b.ring] ?? 9) ||
    a.layer.localeCompare(b.layer) || a.title.localeCompare(b.title));

  // Canonical axial ring walk. The direction order matters: an ad-hoc ordering
  // does not close the loop, and the spiral drifts off in one direction — the
  // first version put every node below the centre and ran off the viewport.
  const DIRS = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]];
  const cells = [[0, 0]];
  for (let radius = 1; cells.length < ordered.length + 6; radius++) {
    let q = -radius, r = radius;                  // centre + DIRS[4] * radius
    for (let i = 0; i < 6; i++) {
      for (let step = 0; step < radius; step++) {
        cells.push([q, r]);
        q += DIRS[i][0];
        r += DIRS[i][1];
      }
    }
  }

  // Scale the cell so the spiral reaches ~0.85 whatever the node count. A fixed
  // step either wasted most of the frame at low counts or overflowed at high.
  const ringsNeeded = Math.max(1, Math.ceil((Math.sqrt(1 + (ordered.length - 1) * 4 / 3) - 1) / 2));
  const S = 0.85 / (1.5 * ringsNeeded + 0.9);
  const pts = ordered.map((n, i) => {
    const [q, r] = cells[i];
    return [S * Math.sqrt(3) * (q + r / 2), S * 1.5 * r];
  });

  // Recentre on the centroid. Guarantees symmetry about the origin whatever the
  // spiral does, so the layout cannot drift out of frame as the count changes.
  const mx = pts.reduce((a, p) => a + p[0], 0) / (pts.length || 1);
  const my = pts.reduce((a, p) => a + p[1], 0) / (pts.length || 1);
  ordered.forEach((n, i) => {
    n.px = pts[i][0] - mx;
    n.py = pts[i][1] - my;
    n.polar = false;
  });
  return {};
}

/* ------------------------------------------------------------------- force */
/* Cheap deterministic relaxation: links pull, everything repels, zones hold a
   loose radial home. Seeded from the ring layout and run to a fixed iteration
   count so the result is reproducible — a force layout that lands somewhere new
   every load is a toy, not a map. */
export function force(nodes, edges, iterations = 260) {
  const idx = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const P = nodes.map((n) => {
    const a = hash(n.id) * TAU;
    const ringR = (RINGS[RING_INDEX[n.ring] ?? 1] || RINGS[1]).r;
    return { n, x: Math.cos(a) * ringR, y: Math.sin(a) * ringR, vx: 0, vy: 0, home: ringR };
  });
  const pos = Object.fromEntries(P.map((p) => [p.n.id, p]));
  const links = edges
    .map((e) => [pos[e.source], pos[e.target]])
    .filter(([a, b]) => a && b);

  for (let it = 0; it < iterations; it++) {
    const cool = 1 - it / iterations;

    for (let i = 0; i < P.length; i++) {
      for (let j = i + 1; j < P.length; j++) {
        const a = P[i], b = P[j];
        let dx = b.x - a.x, dy = b.y - a.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 1e-6) { dx = 1e-3; dy = 0; d2 = 1e-6; }
        if (d2 > 0.36) continue;                  // ignore distant pairs
        const f = 0.00042 / d2;
        const d = Math.sqrt(d2);
        const ux = dx / d, uy = dy / d;
        a.vx -= ux * f; a.vy -= uy * f;
        b.vx += ux * f; b.vy += uy * f;
      }
    }

    for (const [a, b] of links) {
      const dx = b.x - a.x, dy = b.y - a.y;
      const d = Math.hypot(dx, dy) || 1e-3;
      const f = (d - 0.26) * 0.035;
      const ux = dx / d, uy = dy / d;
      a.vx += ux * f; a.vy += uy * f;
      b.vx -= ux * f; b.vy -= uy * f;
    }

    for (const p of P) {
      // hold the zone's radius loosely, so ARMS structure survives the shuffle
      const r = Math.hypot(p.x, p.y) || 1e-3;
      const pull = (p.home - r) * 0.06;
      p.vx += (p.x / r) * pull;
      p.vy += (p.y / r) * pull;

      p.x += p.vx * cool; p.y += p.vy * cool;
      p.vx *= 0.86; p.vy *= 0.86;

      const m = Math.hypot(p.x, p.y);
      if (m > 1.02) { p.x = (p.x / m) * 1.02; p.y = (p.y / m) * 1.02; }
    }
  }

  for (const p of P) { p.n.px = p.x; p.n.py = p.y; p.n.polar = false; }
  return {};
}

export function apply(name, nodes, edges) {
  switch (name) {
    case 'circle': return circle(nodes);
    case 'hex':    return hex(nodes);
    case 'force':  return force(nodes, edges);
    default:       return rings(nodes);
  }
}

export const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);
export const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
