# Writing checklist

For anything a human reads: docs, READMEs, notes, commit messages, PR bodies,
answers.

## Shape

- [ ] **First sentence carries the point.** Not context, not a restatement of the
      question. If the reader stops after one sentence, they should have the
      answer.
- [ ] **Descending importance.** Most people stop reading a third of the way in.
      Anything at the bottom is for the minority who got there.
- [ ] **One idea per paragraph.** Two ideas is two paragraphs.
- [ ] **Headings are navigation.** A reader scanning only headings should get the
      structure of the argument.
- [ ] **No summary of what was just said** unless the piece is long enough that a
      reader could have lost the thread — which is rarer than it feels.

## Words

- [ ] **Cut every word that survives being cut.** Do one pass whose only job is
      deletion.
- [ ] **Concrete over abstract.** A number, a file path, a command, a name.
- [ ] **Active voice by default.** Passive when the actor genuinely does not matter.
- [ ] **No intensifiers.** "very", "really", "extremely", "incredibly" all weaken
      the word they modify.
- [ ] **No hedge stacking.** One qualifier is honest; three is cowardice.
- [ ] **Banned unless load-bearing:** leverage, utilise, robust, seamless,
      comprehensive, holistic, elevate, delve, tapestry, journey, unlock,
      supercharge, game-changing, revolutionary.
- [ ] **Say the number.** "much faster" → "4.6s → 0.3s".

## Honesty

- [ ] **Claims carry evidence.** A number, a source, a file path, or explicit
      "I have not verified this".
- [ ] **Unknowns are stated.** "I could not determine X" is more useful than a
      confident guess, and much cheaper than a confident wrong guess.
- [ ] **Failures are reported as prominently as successes.** A summary that omits
      what broke is a lie of composition.
- [ ] **No praise of the material** you are summarising, and none of the reader's
      question.
- [ ] **Tradeoffs stated.** Anything presented as free has an unstated cost, and
      the reader will find it later and trust you less.

## Formatting

- [ ] **Tables for anything with two or more dimensions.** Prose comparing four
      things across three axes is unreadable; a table is instant.
- [ ] **Lists only for genuinely parallel items.** If the bullets are different
      shapes, it is prose wearing a list costume.
- [ ] **Bold sparingly**, for the one phrase per section a skimmer must catch.
      Bold everywhere is bold nowhere.
- [ ] **Code formatting for anything typed** — commands, paths, identifiers,
      values.
- [ ] **No emoji in technical writing** unless it is a status glyph carrying real
      information in a table.

## Commit messages and PR bodies

- [ ] **Subject: what changed, imperative, under 72 chars.** No "fix bug".
- [ ] **Body: why, and what it costs.** The diff shows what; only you can supply
      why.
- [ ] **Name the bug's mechanism**, not its symptom. "Mode was derived from
      per-run state" beats "fixed status display".
- [ ] **State what was verified**, and how. "Confirmed by deleting 20 vectors and
      watching an incremental run restore coverage" is worth more than "tested".
- [ ] **Surprises get their own paragraph.** The thing that will bite the next
      reader is the most valuable content in the message.
