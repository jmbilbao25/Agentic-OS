---
name: gauntlet-loop
description: Turn a goal into a build-and-critique loop that runs until the work beats a named reference in a blind comparison. Use when quality matters more than speed, when "good enough" keeps shipping, or when asked to gauntlet, loop on, or beat a specific thing. Also documents the /api/gauntlet endpoint that runs this loop inside the second brain.
---

# Gauntlet loop

Adapted from [gauntlet-loop](https://github.com/robonuggets/gauntlet-loop) by
robonuggets, CC BY 4.0. Rewritten for this vault and wired into
`server/gauntlet.py`, which runs the loop against your own notes.

A model asked to produce something good produces something average, because
average is what it was trained to predict. It produces something good when it has
to win a comparison it cannot see the labels on.

## The bar is the whole trick

Everything else is scaffolding. Three tests, and the bar must pass all of them:

- **Named.** A specific artifact, not a category. "Stripe's pricing page" works.
  "Award-winning SaaS sites" does not.
- **Fetchable.** The critic must be able to obtain it — read the page, run the
  binary, open the repo. If it cannot, it will invent the comparison and approve
  everything. This is the most common failure by a wide margin.
- **Comparable.** Both can sit side by side and a judge can pick one. If you
  cannot picture the A/B, it is not a bar.

If the goal has a measurable half — load time, token cost, pass rate, word count —
name it alongside the reference. Taste plus a number beats taste alone.

Prefer the hardest bar the agent can genuinely reach. A bar that is too easy makes
the loop exit on round one, which looks like success and is not.

## The loop

1. Build. One artifact, no commentary.
2. Judge blind. A **separate** agent with **fresh context** sees the candidate and
   the bar as A and B, in random order, labels stripped. It picks one and names
   the single biggest gap in the loser.
3. If the bar won, hand the gap back to the builder and go again.
4. Exit when the critic picks ours. Not on a round count.

## Four ways this fails

- **A vague bar.** Covered above. Check it before spending a round.
- **The builder judging its own work.** The critic must not know how hard the
  builder tried, or how many rounds it has been. Fresh context, separate call,
  ideally a different model.
- **A soft critic.** Give it a binary job: A or B. Scores out of ten drift upward
  every round because each round really is a little better than the last, and
  "7.5/10" never forces a decision.
- **Exiting after N rounds.** A round ceiling is a cost stop. When it triggers,
  the result is a loss — report it as one rather than dressing it up as done.

## Running it here

The second brain has this built in: **Gauntlet** in the dock, or

```
POST /api/gauntlet
{"goal": "...", "bar": "<the reference, in full>",
 "builder_model": "...", "critic_model": "...", "max_rounds": 4}
```

It retrieves from `brain/` first, so the builder argues from your own positions and
vocabulary rather than from general knowledge, and cites the notes it used.

Set the builder and critic to **different models** in Settings. Same model on both
sides is the "builder judging its own work" failure wearing two hats — the app
warns when you do it, and runs anyway, because sometimes it is all you have.

`bar_url` fetches a page instead of pasting it. Private and link-local addresses
are refused: the server holds an API key, so "fetch this URL for me" is a request
to make the server your proxy.

## Prompting another agent instead

When the work belongs somewhere this app cannot reach, hand over a prompt rather
than instructions. Around 120–180 words, plain sentences, no bullet lists inside
it. Name the goal, name the bar as a concrete fetchable thing, say to break the
work into independently judgeable pieces, say the critic is separate and harsh and
compares blind, and say the exit is winning the comparison. Leave architecture,
file layout and round counts out — the agent decides those better than a spec
written before the work started.
