# Mount Truncation — Root Cause & the Verification Protocol That Removes It

## Symptom
When large or just-edited files are read through the Linux **bash mount**
(`/sessions/.../mnt/...`), the mount sometimes serves a **stale or truncated** view:
- `build_market_map.py` (~1875 lines) is served as **1756 lines** — cut mid-statement.
- A just-`Edit`ed module is served as its **pre-edit** copy (stale cache).
- `terminal.html` (~774 KB) is served **without the most recent appended block**.

This breaks bash-side verification (`python3 -c "ast.parse(...)"`, `node --check`,
`node tools/check-scripts.mjs`) even though the file is **correct on disk**.

## Root cause (measured, not assumed)
The sandbox mount is a host→Linux bridge with a read cache that does **not** invalidate
promptly after the file tools (`Write`/`Edit`) write to the real host filesystem. Every
cache-bust technique was tried and **all failed** to recover the full bytes:

| technique | result |
|---|---|
| `wc -l`, `cat > /tmp/x` | 1756 / 1875 lines |
| `dd bs=1M` | 1756 lines |
| `python open().read()` | 1757 lines |
| `posix_fadvise(DONTNEED)` + reopen | 1757 lines |
| fresh-path copy via python | 1756 lines |
| `sync; sleep; reread` (×6) | unchanged |

Conclusion: **you cannot fix this from bash.** The bytes past the boundary are simply not
served. So the fix is to *route verification around the mount* — and to keep files small
enough that the boundary is never hit.

## Authority hierarchy (use this, always)
1. **`Read` / `Write` / `Edit` tools = source of truth.** They read/write the real host FS
   and see the whole file (e.g. `Read` returns line 1777 of a file the mount cuts at 1756).
   If `Edit` reports success, the change is on disk — full stop.
2. **`git show HEAD:path`** reads from git objects, not the mount → authoritative for the
   committed baseline.
3. **CI on real Ubuntu** (`node tools/check-scripts.mjs`, `py_compile`, the auto-discovered
   `test_*.py` / `test_*.mjs` net) is the final gate — no mount involved.
4. **bash mount reads of recently-written/large files = unreliable.** Never trust a bash
   `ast.parse`/`wc` failure on such a file as evidence of a real defect; confirm with (1)–(3).

## The protocol (removes the error class without adding flaws)

### 1. Modularize — keep hot-edited files under the boundary
Empirically, **every module ≤ ~255 lines reads fully through the mount**; only the two
monoliths (`build_market_map.py` 1875 lines, `terminal.html` 774 KB) truncate. So:
- Put **new logic in new small modules** the monolith imports. This is exactly how the new
  verified engines were added — `composite_gate.py`, `trial_ledger.py`,
  `intraday_conviction.py`, `qa_signoff.py`, `fmp_history.py` — all bash-verifiable and
  unit-tested in place, with `build_market_map.py` only gaining a 1–2 line import/call.
- **Recommended next extraction:** lift the price-source hierarchy (`_get_hist` + the FMP
  health tracker) out of `build_market_map.py` into a `price_source.py` module so that
  surface becomes independently testable and the monolith stops growing.

### 2. Client JS — externalize, don't inline
Substantial new terminal logic goes into an external `.js` file loaded via `<script src>`
(the established pattern: `engine.js`, `intraday_engine.js`, `pooled_research.js`,
`quarterly_timeline.js`). Each external file is small and bash-verifiable; `terminal.html`
only gains a `<script src>` line. Reserve inline `terminal.html` edits for small UI glue.

### 3. Verify mount-independently
- **Edited small file won't parse in bash?** It's a stale cache, not a defect. Reconstruct
  the authoritative content into native `/tmp` and run there:
  `Read` the file (authoritative) → write it verbatim to `/tmp/mod.py` via a bash heredoc →
  `python3 /tmp/test.py` with `sys.path` pointed at `/tmp`. (This is how the composite-gate
  / conviction suite was confirmed 27/27 after the mount served stale module copies.)
- **Monolith (`build_market_map.py`)?** `git show HEAD:path` + apply the edits with
  `str.replace(..., 1)` (assert each anchor count == 1) in `/tmp`, then `ast.parse` — fully
  mount-free.
- **Final word is CI.** Push, let the real-Ubuntu job run the script + JSON integrity gate +
  the test net.

### 4. Never "refresh" a mount file in place
Do **not** `cp f f.tmp && mv f.tmp f` (or `mv f f.bak; mv f.bak f`) to try to bust the cache:
the read side is the stale one, so this can overwrite the **authoritative** file with a
**truncated** copy — silent data loss. Only the file tools write authoritative bytes.

## Why this is strictly an improvement
The fix is also better engineering: smaller, single-responsibility modules with their own
unit tests; no monolith growth; deterministic, mount-free verification; and CI as the
backstop. Nothing about the solution weakens the model — it removes a verification failure
mode *and* improves modularity at the same time.
