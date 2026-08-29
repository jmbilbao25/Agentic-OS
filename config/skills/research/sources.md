# Sources

Every source here is **keyless** — no account, no API key, no token. That is a hard
requirement: a scheduled routine that depends on a credential is a routine that
breaks silently months later on a box nobody is watching.

| Source | What it is good for | What it is bad at |
|---|---|---|
| **Hugging Face daily papers** | community-curated, so it pre-filters arXiv volume down to what people actually read | popularity bias; upvotes track novelty and hype more than durability |
| **arXiv** | primary source, newest first, full abstracts | no quality filter at all; preprints are unreviewed by construction |
| **GitHub search** | working code, real adoption signal via stars on *recently created* repos | stars are marketing; a 3k-star repo can be a README |
| **HF trending models** | what *shape* of model is climbing — size, modality, licence | leaderboard position is close to meaningless for your use |
| **Hacker News (Algolia)** | what practitioners argue about; comments often better than the article | fashion-driven, and the top comment is frequently confidently wrong |
| **Lobsters** | smaller, more engineering-flavoured than HN | low volume; many days have nothing |

Deliberately excluded: **Reddit** (403s automated clients), **Twitter/X** (no keyless
read access), and anything behind Cloudflare interactive challenges. Do not add a
source that needs a key without a strong reason.

## Reading each source honestly

- **Papers**: the abstract is a sales pitch. The contribution is usually one
  sentence in the introduction, and the limitation you care about is in a
  subsection near the end that the abstract does not mention.
- **Repos**: check the commit graph, not the star count. A repo with 4k stars and no
  commits in five months is an artifact, not a tool.
- **Models**: licence and size decide whether you can use it; benchmark numbers
  decide nothing.
- **Threads**: the value is disagreement between informed people. A thread where
  everyone agrees teaches you nothing you did not already believe.

## The layer rule

Gathering writes to `brain/raw/`. **Only** to `brain/raw/`.

This is not bureaucracy. An automation that promotes its own output to `brain/wiki/`
produces a vault full of material nobody has read, phrased in nobody's voice, and
indistinguishable from material that was actually understood. At that point the
vault stops being a second brain and becomes a feed with worse search.

Promotion is a human act — or an explicitly instructed one. It requires restating
the idea in your own words, which is also the step that reveals whether you
understood it.

## Provenance format

Every capture carries where it came from and when, in frontmatter:

```yaml
---
captured: 2026-08-29
captured_at: 2026-08-29T03:53:42Z
kind: radar | research
source: automations/radar.py
topic: <the question, for research runs>
---
```

A capture without provenance is a rumour. See
`brain/wiki/Provenance Or It Didn't Happen.md`.
