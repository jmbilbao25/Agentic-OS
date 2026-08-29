---
name: socratic-recall
description: Run a structured self-interrogation of the second brain: challenge vault answers with five Socratic questions (assumptions, staleness, inversion, disagreement, cost) and write confirmations or corrections back to the vault. Use when the user says question the brain, challenge this, stress-test a memory, or before acting on recalled knowledge for a high-stakes decision.
---

# Socratic Recall — interrogate the vault before you trust it

Search answers questions; this skill answers *questions you didn't think to
ask*. Use it before acting on recalled knowledge, before making a decision the
vault influenced, or whenever the user says "question the brain", "challenge
this", or "what are we missing?"

## The loop

Run this cycle at most three times, then commit to an answer:

1. **Answer** — find the best note or memory for the question at hand.
2. **Interrogate** — ask it the five questions below, and actually go look.
3. **Decide** — either the answer survives (state it with confidence) or it
   cracks (write the correction back to the vault).

If you claim the answer survives without having run step 2 against real notes,
you are not doing Socratic recall — you are narrating.

## The five questions

1. **What does this claim assume that nobody said out loud?**
   Read the note, then read one note it links to. The assumption is usually
   hiding in the link, not the text.
2. **When did this become true?**
   `note_history` on the note (or `git log` on its file). A decision made
   before a dependency changed is a candidate for stale, not for truth.
3. **What would have to be different for the opposite to be right?**
   State the condition, then search the vault for whether that condition has
   since arrived. If it has, the note owes a rewrite.
4. **Who disagrees?**
   Search for the opposing phrasing, not just the topic. If nothing in the
   vault disagrees, look for whether the disagreement was never captured —
   that gap is itself a finding.
5. **What does this note cost us if it is wrong?**
   Rank: silently breaks a system → rewrite now; wastes an hour → note the
   caveat; merely misleads → queue it. Spend correction effort by cost.

## Writing back

Every interrogation ends in one of three honest outcomes — never a shrug:

- **Confirmed** — the note stands. If it took real work to confirm, add one
  sentence to the note saying what you checked.
- **Corrected** — edit the note in place; never fork a second note on the
  same subject. If the correction is about memory being wrong, also ingest
  a "Correction: <topic>" document so retrieval learns the newer fact.
- **Condemned** — the note is wrong enough to be dangerous. Rewrite it
  around what is true, keep the filename (inbound wikilinks survive), and
  note in the edit what made you distrust it.

## When NOT to use this

Casual recall ("what did we say about X?") does not need an interrogation —
search and go. Reserve this for decisions, deletions, deployments, and
anything the user is about to rely on.
