# UI checklist

Run this against a rendered screenshot, not against the source. Source looks fine
when the page is broken.

## Structure

- [ ] **One primary action per view.** If two things compete for "the thing you do
      here", one of them is secondary — make it look secondary.
- [ ] **Nothing important below the fold on first load.** The state of the system
      is visible without scrolling.
- [ ] **Empty states say what to do**, not "No data". `no captures yet — bin/os
      capture "Title"` teaches; "Nothing here" abandons.
- [ ] **Loading, empty, error, and full states all designed.** Three of the four
      get skipped by default and they are most of what a user actually sees.
- [ ] **Nothing overlaps.** Check labels against panels, panels against each other,
      text against the viewport edge, at 1280×577 *and* 390×844.

## Type

- [ ] **Two typefaces maximum**, and one of them is monospace for code/paths.
- [ ] **A real scale**, not arbitrary sizes. Four steps is plenty.
- [ ] **Line length 45–90 characters** for prose. Full-width paragraphs are
      unreadable and the single most common web typography failure.
- [ ] **Line height ≥ 1.5** for body text, tighter for headings.
- [ ] **No text below 11px**, and nothing important below 12px.
- [ ] **Numbers that change are tabular** (`font-variant-numeric: tabular-nums`) so
      they stop jittering.

## Colour

- [ ] **One accent.** More than one accent means no accent. If categories need
      colours, that is a categorical palette, not four accents.
- [ ] **Colour is never the only signal.** Add a shape, label, or position — for
      colourblind users and for greyscale screenshots.
- [ ] **Body text ≥ 4.5:1 contrast**, large text ≥ 3:1. Dark themes fail this most
      often: `#666` on `#111` is unreadable and extremely popular.
- [ ] **Dim means dim, not invisible.** Secondary text you cannot read is not
      hierarchy, it is a bug.

## Motion

- [ ] **Motion communicates or it goes.** Enter/exit, position change, state change,
      attention. Ambient motion is allowed exactly once per screen and must be slow.
- [ ] **Interaction feedback under 100ms.** Anything slower feels broken regardless
      of how fast the backend is.
- [ ] **Transitions 120–240ms.** Longer feels sluggish, shorter reads as a jump.
- [ ] **Ease-out for entering, ease-in for leaving.** Linear reads as mechanical.
- [ ] **`prefers-reduced-motion` respected.** Not optional; it is an accessibility
      requirement and some people get sick.
- [ ] **Nothing animates on a loop near text** anyone is expected to read.

## Interaction

- [ ] **Keyboard reachable.** Every action has a key path. `/` to search, `Esc` to
      close, arrows to move, `Enter` to commit.
- [ ] **Focus is visible.** If you removed the outline, you added something better.
- [ ] **Hit targets ≥ 32px** (44px on touch).
- [ ] **Destructive actions are undoable or confirmed** — pick one, never neither.
- [ ] **State survives reload** where it plausibly should.
- [ ] **Optimistic where it is safe.** Filter locally on keystroke, reconcile with
      the server when it answers. Waiting on a round trip to filter a list you
      already have is a self-inflicted wound.

## Data display

- [ ] **Real data, never lorem ipsum.** Placeholder data hides every layout bug
      that real data finds — long titles, missing fields, zero rows, 900 rows.
- [ ] **Longest realistic value fits.** Test with the longest title in the corpus.
- [ ] **Precision matches meaning.** `247MB` not `247.3841MB`. `2 minutes ago` not
      a timestamp, unless the timestamp is the point.
- [ ] **Partial states are labelled as partial.** `40/66 vectors · indexing` beats
      `40 vectors`, which reads as data loss.

## The two-minute audit

1. Screenshot it. Look at the screenshot, not the app.
2. Squint until text is unreadable. Does the hierarchy still work? If everything
   is the same weight, there is no hierarchy.
3. Greyscale it. Is anything now indistinguishable?
4. Read every string aloud. Cut every word that survives being cut.
5. Ask of each element: what question does this answer? Delete the ones with no
   answer.
