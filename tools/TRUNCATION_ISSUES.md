# Truncated / stale sandbox file views — issue catalog & solutions

**Root cause (one sentence).** The agent edits files on the authoritative Windows filesystem (Read/Write/Edit
tools), but the Linux *bash sandbox sees those files through a bind-mount that lags and serves stale or
byte-truncated copies of large or freshly-written files*. So `cat`, `grep`, `python -m py_compile`, `node --check`,
and `node <file>` run in bash can report a complete, correct file as broken/truncated/"null bytes" — a
**trust-boundary error**, not real corruption. (This is exactly the failure class in
*Hardened Workflow Report for Preventing Stale and Truncated Sandbox File Views*.)

**Universal resolution rule.** When a bash read disagrees with the editor's write confirmation, the Read tool,
`check-scripts.mjs`, or CI, the **authoritative re-read and CI win**. Never "fix" a file because the mount shows
it truncated.

---

## Issues faced this session, and the fix applied to each

| # | File | Symptom in bash | Reality | Fix applied |
|---|------|-----------------|---------|-------------|
| 1 | `tools/run-checks.sh` | 1369 bytes, control bytes in tail, "Unterminated quoted string" | prior write got cut mid-line | **Rewrote clean** (filesystem-discovery of tests); syntax-checked in native `/tmp` |
| 2 | `tools/test_intraday.mjs` | `SyntaxError` at `ok('rando` (cut at 4499 B) | file intact through line 85 | Verified via Read tool; CI runs the real file |
| 3 | `tools/market_map/build_market_map.py` | bash saw 1466 lines; `synth()/main()` "missing" | real file ~1590+ lines, `main()` at 1523 | Read tool for the tail; trusted CI |
| 4 | `tools/market_map/options_analytics.py` | `py_compile` → "source code string cannot contain null bytes" | clean (import line correct) | Read-tool verify of edited region |
| 5 | `marketmap.json` | `verify_artifact guard` read truncated mid-array at 443,473 B (`…"label":"Rough`) | file valid + live on the site | Run the **guard in CI** (authoritative runner FS), not the sandbox |
| 6 | `terminal.html` (many edits) | `py_compile`/`grep` saw stale or truncated content | edits applied; inline JS balanced | Edits via Edit tool (real FS); verified by `node tools/check-scripts.mjs` which reads real files (22/22 → 23/23) |
| 7 | `tools/market_map/emit_static.py` | `grep` reported "no json.dump" | writes present | Read tool to locate the real write sites |
| 8 | `tools/market_map/test_stats_ref.py` | ran truncated → `'(' was never closed` (line 66) | file complete; tests pass | Reconstructed in native `/tmp`, ran there → 9/9 |
| 9 | `tools/test_stats_parity.mjs` | ESM `SyntaxError` at final line (truncated) | file complete | Ran the logic from native `/tmp` against real `engine.js` → all parity passed |
| 10 | `engine.js` (after the tier move) | `node --check` → "Unexpected end of input" at line 38 | file complete, closes at line 87 | Read-tool confirm + **`/tmp` math proof** of every moved estimator |
| 11 | `tools/market_map/intraday_engine.py` / `tiingo_connector.py` | "null bytes" / stale on freshly-edited large files | clean | Read-tool verify; trust CI |

---

## The standing solution set (already built into the repo)

1. **`tools/verify_artifact.py`** — atomic write (same-dir temp → `fsync` → `os.replace` → re-read + sha256
   verify), plus `manifest` / `verify` / `guard`. The acceptance boundary is the authoritative re-read, never a
   shell `cat`. `emit_static.py` writes every card through `write_atomic`.
2. **CI is the authority** — `ci.yml` runs `run-checks.sh` + an HTML tail-check, and `pages.yml` runs
   `verify_artifact guard` on the promoted `marketmap.json`. GitHub runners have no bind-mount lag, so a
   genuinely truncated artifact fails the build instead of shipping.
3. **`tools/check-scripts.mjs`** reads the real HTML files and validates every inline `<script>` — the reliable
   local gate for `terminal.html` (the mount-truncated `py_compile`/`grep` are not authoritative for it).
4. **Cross-language golden fixtures** (`stats_golden.json` + `test_stats_parity.mjs`) and the **shared
   `engine.js`** mean estimator correctness is checked against a stored reference, immune to which view of a
   working file the shell happens to serve.
5. **`tools/VERIFICATION_POLICY.md`** codifies the rule for humans and agents.

## Operating procedure when bash shows a freshly-edited file as broken
1. Confirm the real file with the **Read tool** (authoritative) — check the tail closes correctly.
2. To *run* logic that the mount truncated, **reconstruct it in native `/tmp`** (not the bind-mounted path) and
   execute there.
3. Treat **CI** (which checks out the real committed tree) as the final word.
4. Do **not** rewrite a file that the editor already wrote correctly just because bash shows it cut off.
