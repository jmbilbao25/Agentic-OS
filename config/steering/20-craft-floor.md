---
inclusion: auto
name: craft-floor
description: The mechanical quality bar for any interface in this repo — contrast, type, spacing, motion, states, and the browser surfaces that ship unthemed. Also the list of defaults to refuse. Use when creating or editing anything under server/static/, docs/, or any HTML, CSS, or UI code.
---

# Craft floor

Distilled from [impeccable](https://github.com/pbakaus/impeccable) by pbakaus and
[taste-skill](https://github.com/Leonxlnx/taste-skill) by Leonxlnx, then narrowed
to what this repo actually builds: one dark, data-dense instrument panel.

The floor holds the mechanics. It never picks the direction.

## Verify on the built result

Each of these is a check on what rendered, not on what you intended.

- **Contrast.** Body and placeholder text ≥4.5:1, large text ≥3:1. Read the
  computed values; do not eyeball a dark theme. Every text token in `app.css`
  carries its measured ratio in a comment, and `.uitest/ui.mjs` recomputes them
  on every run.
- **Depth.** Shadows carry an offset *and* a soft blur. A zero-offset coloured
  halo is decoration, not depth.
- **Spacing.** Tight groups, generous separation. More space above a heading than
  below it — the heading belongs to what follows.
- **Type.** Body measure 65–75ch. Tracking floor −0.04em. Balanced headings.
  Obvious scale and weight steps. Run the real content at every breakpoint and fix
  what overflows.
- **Motion.** One authored moment, not scattered effects, and not the same
  entrance on every element. Exponential ease-out from an already-visible default.
  Honour `prefers-reduced-motion` — and shorten transitions there rather than
  removing them, because an instant state change reads as a glitch.
- **States.** Hover, active, focus, disabled, loading, error, empty. All of them,
  with real content in them.
- **Disabled controls still have to be readable.** Do not fade a filled button
  with `opacity` — it takes the label down with it and produces a button with no
  visible text. Declare the disabled colours.
- **Browser surfaces.** The parts you did not draw still carry the design:
  selection, caret, scrollbars, focus rings, placeholders, underline offset,
  tabular numerals for anything that changes in place, `accent-color`. This is the
  cheapest signal that a page was built rather than assembled, and the one that
  gets skipped most reliably.
- **Glyph coverage.** A subset webfont plus an unusual glyph equals a tofu box.
  `⌘`, `↵` and `⇧` are outside a latin subset and missing from the default Linux
  monospace. Spell the key out, or branch on the platform.
- **Keyboard.** Every action reachable without a mouse, and shortcuts must not die
  because focus is parked in a control where the letter means nothing.
- **Copy.** The product's own language. Controls name their action. Errors name
  the problem *and* the recovery.

## Refuse

These are the category's defaults, not bans — the brief's own words can earn any of
them. Reaching for one when the choice was free means you were not deciding.

- Same-size cards of icon + heading + text as the page structure. Cards are the
  lazy container; nested cards are always wrong.
- An eyebrow or kicker above a heading. This one is a real ban: the heading carries
  its own weight.
- Section numbers (01 / 02 / 03) unless the sequence carries information.
- Meta-labels as headings — "SECTION 04", "QUESTION 05", "ABOUT US".
- Gradient text. Emphasis comes from weight or size.
- Glass and blur as decoration rather than as a specific effect. Backdrop blur is
  earned only where a surface genuinely sits over live content.
- A coloured `border-left` above 1px on cards, list items or callouts.
- Hard offset shadows (`box-shadow: 4px 4px 0`) outside a world that actually chose
  neobrutalism.
- Sparklines, progress rings and soft-shadowed rounded rectangles standing in for
  content.
- Monospace as a costume for "technical". Mono is for code, paths, ids and
  numbers — things where character alignment means something.
- Emoji or a unicode glyph standing in for an icon. Icons are drawn, in one
  consistent stroke weight.
- A system sans as the *display* voice. Self-host a face with a character that
  matches the world. (System mono for data is fine.)

## This repo's world

Dark mission-control instrument panel. The vault is telemetry from a running
system: data is monospaced and tabular, chrome is quiet, and the map is the only
thing allowed to glow. The ARMS ring hues are the colour system — skills and core
orange, memory violet, routines amber, applications cyan — and the UI reuses them
rather than introducing a second palette. Display face is Space Grotesk, bundled
and subset under `server/static/fonts/`; no font CDN, because a private instance
should not be making third-party requests.

When torn between refined and committed, commit.
