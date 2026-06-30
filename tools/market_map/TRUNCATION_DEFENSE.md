# Truncation defense — alerting + mount-free verification

## What "truncation" is here, exactly

The Claude sandbox reads repo files through a FUSE mount that **byte-caps** large/edited files. Two
distinct failure modes follow, and they are NOT the same:

| | where the bad bytes live | who sees it | reaches production? |
|---|---|---|---|
| **Mount-read artifact** (common) | only the sandbox's *view* | `bash`/`cp`/`git` inside the sandbox | **No** — the host file & commit are complete |
| **Disk truncation** (rare, dangerous) | the actual file on disk | everyone, incl. the next commit | **Yes, if committed** |

The Read/Write/Edit tools talk to the **host** file and are authoritative. `bash`, `cp`, and even
`git` inside the sandbox read the **mounted** (truncatable) copy. That asymmetry is the whole problem:
a sandbox `py_compile` or `git diff` can report a "truncated" file that is actually fine on disk
(false alarm), and — once, this session — a file (`projledger.py`) was genuinely truncated on disk and
would have shipped broken.

## How a truncated block corrupts our DATA (the impact chain)

A truncated **source** file doesn't just look wrong — it changes what we publish:

- `build_market_map.py` truncated → `marketmap.json` build raises → site serves **stale** board (or empty).
- `projledger.py` truncated → `projlearn.json` never builds → terminal cone runs **uncalibrated**.
- a `*_panel.js` truncated → that `<script>` throws at load → a tile **silently disappears**.
- a committed `*.json` truncated → browser reads **partial JSON** → wrong numbers or a hard parse error.

## The alert: `truncation_sentinel.py`

`tools/truncation_sentinel.py` scans every tracked `.py/.js/.mjs/.json/.jsonl/.csv/.html` and, for each
truncated/broken file, prints **the symptom, the downstream data it affects, HOW it breaks, and the fix**,
emitting GitHub `::error::` annotations and exiting non-zero. With `--git-baseline` it also flags any file
that shrank >25% versus `HEAD` (a truncation tell even when the remnant still parses).

It runs in three places (defense in depth):

1. **`tools/run-checks.sh`** — the offline suite (so `ci.yml` gates every push/PR).
2. **`.github/workflows/pages.yml`** — an *early* gate, before the build, so corrupted source can
   **never deploy** (`--git-baseline`).
3. **`.githooks/pre-push`** — on **your machine's complete files**, before anything reaches GitHub.

Run it yourself any time:

```sh
python3 tools/truncation_sentinel.py --git-baseline --root .
```

## Better mount-free solutions (ranked)

1. **Host pre-push hook = the real fix.** You commit from your own machine, where files are complete.
   Enabling the hook makes truncation impossible to push:

   ```sh
   git config core.hooksPath .githooks      # one-time, per clone (Git Bash on Windows)
   ```

   It runs the sentinel + full `run-checks.sh` on the true on-disk files and blocks the push on any failure.

2. **CI on GitHub's clean runners is authoritative.** GitHub checks out a fresh, unmounted tree, so its
   `py_compile`-all, `node --check`-all, the test suite, and the sentinel reflect *exactly* what shipped —
   never the sandbox's truncated view. Green CI = clean deploy. This is the source of truth, not sandbox `bash`.

3. **Never `git add`/`commit`/`push` from the sandbox.** Those would stage the truncated *mounted* copy.
   All commits originate from the host.

4. **Agent-side verification uses the reconstruction protocol** (see `SANDBOX_VERIFY.md`): pull authoritative
   content via the Read tool → write to native `/tmp` (not the mount) → run there. Sandbox `bash`/`cp`/`git`
   results are treated as untrusted for content; a "failure" is re-checked against the host Read tool before
   it's believed.

5. **Prefer new files / full rewrites over in-place edits of large files** when working in-sandbox, and keep
   engine modules small (already done via modularization) so any single file stays under the cap and round-trips
   cleanly.

## One-line mental model

> Sandbox `bash` view = *suspect*. Host Read tool + GitHub CI + the pre-push hook = *authoritative*.
> The sentinel turns "is anything truncated?" from a manual worry into an automatic, explained, blocking alert.
