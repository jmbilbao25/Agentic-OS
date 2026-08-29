---
created: 2026-08-29
tags: [ui, layout, canvas]
---

# Frame Beats Canvas

Lay out against the region that is actually **visible**, not the element you are
drawing into. On any interface with floating chrome — a rail, a topbar, a dock —
those are different rectangles, and the difference is often a fifth of the width.

The failure is invisible in radial designs and obvious in linear ones. A circle
centred in the canvas still looks centred whatever overlaps it, because the
overlap trims the same shape from every side of your attention. A horizontal line
centred in the canvas runs straight underneath the rail, and its left end — which
in a ranked line is the *most important* end — is the part that disappears. The
AgentOS map carried this bug through its entire ring-only life without a symptom,
then surfaced it within a minute of the first horizontal layout: 36 notes packed
into a third of the available width, the five best results hidden behind the
legend.

So the layout's input is a frame, `{ x0, x1, y0, y1 }`, and it is **measured from
the DOM** rather than hardcoded. Hardcoding fails on the cases you care about:
the rail is hidden on narrow viewports, and the dock is user-resizable.

Two corollaries worth keeping separate:

- **Insets are per-edge; chrome is not.** A full-height left inset that clears the
  rail also forbids the empty corner *above* the rail. Use insets for the
  arrangement, where uniformity matters more than squeezing an extra column, and
  exact obstacle rectangles for labels, where every reclaimed spot is a name the
  user gets to read.
- **Not every overlay deserves a reflow.** The dock covers part of the map, but
  rearranging the entire map each time you open a note is far more disorienting
  than a few dots being covered while you read it. It joins the label obstacles
  and stays out of the layout frame.

The general form of this: *coordinates are meaningless without the region they are
relative to*, and the element you render into is rarely that region.

Related: [[Taste Is A Checklist]], [[Progressive Disclosure]]
