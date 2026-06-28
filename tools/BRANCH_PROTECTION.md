# Branch protection — make verification authoritative (not just local)

A local pre-commit hook is **bypassable** with `git commit --no-verify` / `git push --no-verify`, so it is a
guardrail, not a policy. To make "nothing ungated reaches GitHub" actually true, the `verify` CI job
(`.github/workflows/verify.yml`) must be a **required status check** on the protected branch. This is a
one-time GitHub settings change only a repo admin can make (it is an access-control action, so it is not
something the build tooling can do for you).

## One-time setup (repo admin)

1. Push the branch that contains `.github/workflows/verify.yml` so GitHub registers the `verify` check.
   Open one PR so the check runs at least once (required checks only appear in the picker after a first run).
2. GitHub → **Settings → Branches → Add branch protection rule** (or **Rulesets → New branch ruleset**).
3. Branch name pattern: `main`.
4. Enable **Require a pull request before merging** (recommended) and **Require status checks to pass
   before merging**.
5. In the status-checks search box, select **`verify`**. Optionally also enable **Require branches to be up
   to date before merging**.
6. (Recommended) Enable **Do not allow bypassing the above settings** so admins are held to the same gate.
7. Save.

After this, a PR cannot merge into `main` unless `verify` (which runs `tools/verify_all.sh`:
`py_compile` of all Python, every `test_*.py` + `test_*.mjs`, inline/external script checks, the file-size
budget, JSON validity, and every payload schema/contract) passes. That is the difference between
"we have quality rituals" and "the repository refuses bad state."

## Local fast feedback (complements, does not replace, the gate above)

```
pip install pre-commit
pre-commit install --install-hooks   # installs pre-commit + pre-push stages from .pre-commit-config.yaml
```

- `pre-commit` stage: inline-script check + file-size budget (fast).
- `pre-push` stage: full `tools/verify_all.sh`.
- Skip ONE hook intentionally with `SKIP=verify-all git push` rather than blanket `--no-verify`.
