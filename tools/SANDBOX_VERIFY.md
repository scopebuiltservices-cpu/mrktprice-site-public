# Verifying engine code reliably (avoid the stale-read trap)

**Root cause of the "mount truncated… retrying" churn:** files written by the editor land on the host
filesystem, but the shell sandbox that *runs* tests sees a separate, lagging view of those files, so a
freshly-written file can read back stale / truncated / NUL-filled. Retry loops fight the symptom.

**The strategy (in priority order):**

1. **Author runnable artifacts natively, run in place, then promote.** For a new engine/module + its test,
   write them with a native shell heredoc into a sandbox temp dir (`/tmp/...`), run them there (coherent
   immediately), and only after green, mirror the verified bytes to the repo with the editor. The bytes you
   ran == the bytes you commit.
2. **For edits to large existing files** (terminal.html, build_market_map.py): use the editor (host-
   authoritative) and lean on CI — do NOT trust the shell's read-back to "verify". A targeted authoritative
   re-read of just the edited span is fine for a structure check; a full-file `python3 -c ast.parse` over a
   freshly-edited big file is not (it'll spuriously fail on a stale read).
3. **Coherence guard before trusting any shell read** of a tool-written file: read it twice and compare a
   hash; if they differ, or the file contains NUL bytes, or is shorter than expected, treat the read as
   stale and re-emit/re-copy — never run the test against it. `tools/coherent_run.sh` does this.
4. **CI on a clean filesystem is the final gate.** It has no mount layer; `verify_all.sh` + the committed
   tests are authoritative.
