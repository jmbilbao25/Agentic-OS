---
date: 2026-08-29
status: accepted
---

# Layout is a pure function, the renderer owns motion

## Context

The map had one shape — concentric ARMS rings — which answers structural
questions well and ranked ones not at all. A ring has no beginning, so "what did
my search find, best first" could only be read by hunting around a circle. Adding
more arrangements meant deciding where arrangement logic lives relative to the
600-line canvas renderer that already owned spin, camera, picking and labels.

## Decision

A layout is a pure function from nodes to positions in **normalised units**:
origin at the scene centre, one unit is `unit` pixels, y down. It knows nothing
about time, zoom, the camera, or the canvas. `server/static/js/layouts.js` holds
four of them; `orbit.js` holds everything that moves.

Two consequences fall out of the split rather than being designed:

- **Switching layouts is an animation, not a redraw.** The renderer keeps an
  anchor per node and interpolates from it, so a change of layout is a tween it
  already knows how to do. This is not decoration: you can follow one dot from its
  ring into its place in the line, and that continuity is the entire reason a
  spatial map beats a list. A jump-cut destroys it on every click.
- **Orbital drift stays out of the layouts.** `rings` returns an angle and a
  radius and the renderer adds `spin`. No layout has a clock.

Layouts receive the **usable frame** — the region not covered by the rail and
topbar, measured from the DOM — not the canvas box. See [[Frame Beats Canvas]].

## Tradeoff

What this costs us:

- Two files to read instead of one, and a contract between them that is
  convention rather than types: a layout must set either `pa`/`pr` with
  `polar: true`, or `px`/`py` with `polar: false`, and must tag `slot` so the
  renderer can stagger labels. Nothing enforces it but the self-check.
- Layouts must report their own row gap so the renderer can size label stacks.
  That is a leak — a geometry function telling a text renderer about typography
  headroom — accepted because the alternative is labels from one row drawn over
  the dots of the row above, and only the layout knows how much room it left.
- Every layout runs over all nodes on any reflow. At vault scale (tens to low
  thousands) this is microseconds; a force simulation would not have been, which
  is a second reason none of these are force-directed.

## Alternatives rejected

- **Positions computed inside the renderer, as before.** Simplest, and how the
  ring view worked. Rejected because there is then no "previous position" to tween
  from and no way to test placement without a canvas. The self-check that caught
  the frame bug, the ragged-row bug and the burst-collision bug cannot exist in
  that design.
- **A force-directed graph.** The obvious move for a wikilink graph, and wrong
  here: it reshuffles on every visit, so nothing is ever where you left it. Also
  ruled out by [[Grep Beats Embeddings Here]]'s premise — this vault is small and
  its structure is already known, so simulating it discovers nothing.
- **Layouts in screen pixels.** Removes the normalisation step, and breaks the
  moment the window resizes or the camera zooms, because every layout would then
  need to know about `view.k`.
