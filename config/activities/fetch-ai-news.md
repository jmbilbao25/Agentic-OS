---
name: fetch-ai-news
description: Capture today's AI signal from six keyless feeds into brain/raw/, then triage it into a digest in brain/output/. Press this for "what happened in AI today".
---

# Fetch ai news

Was a skill that told an agent to run `bin/os brief`. It is an activity now,
because the thing it described needed no agent — it needed a button.

`radar` reads Hugging Face papers and models, arXiv, GitHub trending, Hacker News
and Lobsters, none of which need a key, and writes one dated capture. `distill`
then runs the LLM triage over that capture and writes the digest.

The order is the whole recipe: distilling before capturing would confidently
digest yesterday's news. If `radar` finds nothing it writes nothing and exits
non-zero, so this activity stops rather than producing an empty digest.

`distill` needs an inference key. If it 429s on a free-tier model, the capture is
already safely on disk — re-run and only the digest step repeats.

## Steps

- radar
- distill
