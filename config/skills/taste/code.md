# Code checklist

## Names

- [ ] **A name says what it is, not what it is made of.** `chunks_vec` not
      `sqlite_table_2`. `locked_for(ip)` not `check_ip`.
- [ ] **Boolean names read as assertions.** `partial`, `auth_configured`,
      `available` — not `flag`, `status`, `check`.
- [ ] **Functions that return are nouns; functions that act are verbs.**
      `coverage()` returns, `reindex()` acts. A function that does both wants
      splitting.
- [ ] **No Manager, Helper, Util, Handler, Service, Processor** unless the domain
      genuinely uses the word. They are placeholders for a name you did not find.
- [ ] **Consistent vocabulary.** Pick `doc` or `document` and never mix them.

## Shape

- [ ] **One reason to exist per module.** `vault.py` is the only file that knows
      the on-disk layout; that is why the layout can change.
- [ ] **Dependencies point one way.** If two modules import each other, one
      concept is in the wrong place.
- [ ] **No abstraction before the second use.** Extracting on the first use
      guesses at the axis of variation and usually guesses wrong.
- [ ] **Configuration in one place**, read from the environment, never scattered
      as literals.
- [ ] **Nesting ≤ 3.** Deeper means an early return or an extracted function is
      waiting.

## Failure

- [ ] **Fail closed on security, fail open on features.** An unset password denies
      everyone; a missing embedding model degrades to keyword search.
- [ ] **Every error message names the fix.** "re-run adapters/install.sh" beats
      "binding mismatch".
- [ ] **Absence is a designed case.** Missing file, empty list, no results, no
      credential — decide the behaviour instead of discovering it in production.
- [ ] **Never swallow silently.** Catching to keep going is fine; catching to hide
      is not. Log with enough context to act on.
- [ ] **Partial success is reported as partial.** Returning a count of what worked
      and what did not beats a boolean.
- [ ] **Reconcile against desired state, not against the diff.** Change-detection
      alone cannot repair damage — the reason an incremental index needs a backfill
      pass.

## Comments

- [ ] **Comment the why, never the what.** The code says what.
- [ ] **Document the surprise.** Non-obvious constraints, measured values, and
      things that look wrong but are not. `# fastembed's query_embed() is a no-op
      for this model — measured, cosine 1.0000` saves the next reader an hour.
- [ ] **Record the rejected alternative** where the choice looks arbitrary.
- [ ] **No comment restating the signature**, no `# TODO` without a name or a
      condition, no commented-out code — that is what git is for.
- [ ] **Numbers carry provenance.** `MemoryMax=700M` deserves a note saying the app
      measured 247MB.

## Verification

- [ ] **Prove the guard fires.** A check you never saw fail is a check you cannot
      trust. Break it deliberately once.
- [ ] **Exit code 0 is not evidence.** Assert on the observable outcome — row
      counts, HTTP status, rendered DOM, file contents.
- [ ] **Test the negative path** for anything security-related: wrong password,
      wrong user, lockout, unset credential, expired session.
- [ ] **Measure before optimising**, and write the number down next to the change.
- [ ] **Deploy is a test.** Some bugs only exist on the real box: sandboxed
      systemd units, real memory limits, real timers racing your reads.

## Dependencies

- [ ] **Justify each one against the stdlib.** PBKDF2 is in `hashlib`; BM25 is in
      SQLite. Both were dependencies avoided at zero cost.
- [ ] **Prefer a file to a service.** `sqlite-vec` over a vector database is one
      fewer process to keep alive at 3am.
- [ ] **Pin versions** for anything that ships.
- [ ] **A dependency you cannot explain the need for is a liability**, especially
      one that pulls a hundred transitive packages.
