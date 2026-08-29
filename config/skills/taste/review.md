# Review checklist

Run this on your own work before calling it done. Reviewing your own output is the
highest-leverage habit available, and the one most often skipped because the work
already feels finished.

## Order

Review in this order. Later passes are wasted if an earlier one fails.

1. **Does it work?** Not "does it run" — does it produce the correct observable
   outcome? Check the actual artifact: the rendered page, the row count, the HTTP
   status, the file on disk.
2. **Does it fail well?** Break it on purpose. Wrong input, missing credential,
   empty corpus, no network. Then read the error message as a stranger would.
3. **Is it honest?** Every claim in the output — status indicators, summaries,
   commit messages — must match reality. This is the pass that catches a status
   pill saying `hybrid` on a keyword-only index.
4. **Is it the smallest thing that works?** Delete, then re-check.
5. **Does it read well?** Only now run the writing or UI checklist.

## The questions that find real problems

- **What did I verify, and what am I assuming?** Say both out loud. Assumptions
  written down get checked; assumptions in your head get shipped.
- **What is the most expensive thing I could be wrong about here?** Check that
  first, regardless of how likely it is.
- **What did I not test?** Name it explicitly. "I have not tested this across a
  restart" is a legitimate deliverable; silence is not.
- **What would a hostile reader attack?** Fix that, or say why it is acceptable.
- **If this breaks at 3am, what will the log say?** If the answer is "nothing
  useful", the logging is not done.
- **What is now stale?** A change usually invalidates a doc, a comment, a config
  example, or a note. Update it in the same pass — a stale pointer is worse than
  no pointer.

## Claiming completion

Never say done without naming the evidence. The pattern:

> Done: `<what changed>`. Verified by `<the specific observation>`.
> Not verified: `<what remains unproven>`.

A summary with no "not verified" line is almost always incomplete rather than
perfect.

Specifically forbidden:

- "Should work" — either it does and you checked, or you did not check.
- "Fully tested" without saying what the tests assert.
- Reporting a command's exit code as proof of behaviour.
- Omitting a failure because a later attempt succeeded. The failure is often the
  most useful thing you learned.
- Ticking a step that is partly done. Partly done is not done — untick it and say
  which half is missing.

## Reviewing someone else's work

- Lead with the thing that would cost the most if unaddressed. Ordering by file
  position buries the important note in the middle.
- Separate **must fix**, **should fix**, and **preference**. Unlabelled feedback
  makes every note feel mandatory and the review feel hostile.
- Attack the artifact, never the author.
- If you cannot name what is wrong, do not file the note yet. "Feels off" is a
  prompt to look harder, not a review comment.
