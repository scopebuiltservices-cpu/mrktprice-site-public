# Sandbox verification protocol (FUSE mount trust boundary)

## The problem
When files are edited through the agent's file tools, the sandbox's FUSE mount can serve a **stale, byte-capped
(truncated) copy** of those same files to `bash`/`python`/`cp`. The truncation is **stable** (the same byte
count every read), happens **mid-file** (often mid-statement, producing spurious `SyntaxError`/`AttributeError`),
and is **not cleared** by re-editing, `sync`, `sleep`, `stat`, or a full rewrite. The agent's **Read tool**
(host channel) returns the complete, authoritative file; `bash` does not. New files created in the session sync
fine — only in-place edits get a stale cache entry.

Net effect: `python3 test_*.py` run directly over the mount can fail on truncated modules **even though the
host files are correct**. This is an infrastructure artifact, not a code defect.

## The authoritative gate
CI runs `tools/run-checks.sh` / `tools/verify_all.sh` on a **clean git checkout**, where no mount cache exists
and every file is complete. All `test_*.py` are auto-discovered (`find tools -name 'test_*.py'`). **CI is the
source of truth for green/red.**

## Running the real suite in-sandbox anyway (reconstruction protocol)
To verify edited modules in-sandbox without waiting for CI:

1. Identify corrupted-on-mount files: for each edited module, `py_compile` it and `grep` for a symbol the edit
   added. Compile error or missing symbol ⇒ the mount copy is truncated.
2. For each corrupted file, read the **full** content with the Read tool (host-authoritative) and write it into a
   native, non-mount directory (`/tmp/<dir>/`) via a quoted heredoc. Files that compile + contain their new
   symbols are intact on the mount and can be `cp`'d directly.
3. Copy the committed `test_*.py` (new files sync fine) into the same `/tmp` dir.
4. `cd /tmp/<dir> && python3 -B test_*.py` — a genuine run against authoritative content.

This was used to prove `test_audit_fixes2.py` (intraday decision rule, VRP forward, parity firewall, BL
negative-mass, conformal order-statistic, HARQ label, DK date-honesty) and `test_sens_gate.py` (macro
significance gate) **green in-sandbox**, not merely "deferred to CI".

## Rules
- The Read tool is authoritative for host content; `bash` reads are not, for session-edited files.
- **Never** `git commit`/`git add` from the sandbox over the mount — it would stage the **truncated** copy. The
  user commits from the host, where files are complete.
- Standalone math harnesses (copying the exact function bodies into `/tmp`) verify equations independent of the
  mount; the reconstruction protocol above additionally verifies the **integrated** code path.
