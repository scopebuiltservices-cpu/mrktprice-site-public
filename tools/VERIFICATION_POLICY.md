# Artifact verification policy

The acceptance boundary for any generated file is **re-reading the final bytes from the
authoritative target path and matching a manifest** (sha256 + byte count + tail sentinel).
A filesystem *view* — a `cat`, an IDE pane, a sandbox bind-mount — is a diagnostic hint, not proof.

## Why this exists

This repo is edited from a sandbox whose bind-mount can serve **stale or truncated views** of a
freshly written large file. Running `python3 -m py_compile` or `cat` against the mount can report a
big file (e.g. `terminal.html`, `marketmap.json`) as broken when the authoritative file on disk is
complete and correct. That is a *trust-boundary* error, not a real corruption: the observer and the
writer are not on the same filesystem surface.

**Resolution rule:** when a shell read disagrees with the editor's authoritative read or with CI,
the authoritative re-read and CI win. Do not "fix" a file because the mount shows it truncated.

## The tool — `tools/verify_artifact.py` (stdlib only)

- `write_atomic(path, data)` — same-directory temp → `flush` → `os.fsync` → `os.replace` →
  re-read + sha256 verify. The rename is atomic only within one filesystem, so the temp is created
  beside the target (never staged in `/tmp` and promoted across volumes).
- `manifest <paths…> --out m.json` / `verify <m.json>` — record and re-check sha256/bytes/tail.
- `guard <path> [--min-bytes N] [--ends-with S]` — fail loudly on a missing / empty / truncated /
  wrong-sentinel promote.

## Where it runs

- **CI is authoritative.** The nightly (`pages.yml`) hard-gates `marketmap.json` with
  `guard --min-bytes 5000 --ends-with '}'` after promotion and emits a sha256/byte/tail manifest as
  the forensics layer. The GitHub runner has no mount illusion, so a genuinely truncated promote
  fails the build instead of shipping a half-written map.
- **`test_verify_artifact.py`** (auto-discovered by `run-checks.sh`, run in a fresh process) includes
  a **stale-view detection test**: it manifests a file, truncates it, and asserts the mismatch is
  caught. It uses native `/tmp`, so it is unaffected by the bind-mount and passes locally and in CI.
- The artifact guard is intentionally **not** in `run-checks.sh`, because run-checks is also run
  locally against the mount, where it would false-fail on the truncated view.

## Agent checklist

1. Trust the editor's write confirmation and CI; treat sandbox shell reads of large freshly-edited
   files as hints only.
2. Verify new/small files in native `/tmp` (not the mount) when a byte-exact check is needed.
3. For build outputs, rely on the CI `guard` + manifest, not a local `cat`.
4. One file, one writer, one transaction, one verification.
