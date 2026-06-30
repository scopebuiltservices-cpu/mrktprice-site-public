# mrktprice-site-public

Public website for **[mrktprice.com](https://mrktprice.com)** — the MrktPrice market terminal
(`terminal.html` / `marketmap.html`) and the **Opportunity News** reports (`reports/`).

This repo holds **both** the published site files **and** the analysis/build source code that produces
the published data: the nightly market-map build engine, connectors, econometric/forecast modules,
tests, and GitHub Actions workflows all live here under **`tools/market_map/`** and `tools/`. (Earlier
versions of this README said analysis code lived in a separate private repo — that is no longer true;
the pipeline is now self-contained and self-publishing from this repository.)

© 2026 MrktPrice™ / Marc Jones. All rights reserved. Research/education only — **not investment advice.**

---

## What's in here
| File | Purpose |
|---|---|
| `index.html` | The self-contained dashboard (opens in any browser, no server) |
| `reports/index.html` | Opportunity News list page — **auto-generated**, don't hand-edit |
| `reports/report-template.html` | Drop-in template for a new report (not published) |
| `reports/YYYY-MM-DD-*.html` | Your published reports |
| `build_reports.py` | Regenerates `reports/index.html` from the report files |
| `CNAME` | Custom domain (`mrktprice.com`) |
| `.nojekyll` | Tells GitHub Pages to serve files as-is |
| `404.html` | Branded "page not found" page |
| `robots.txt` | Lets search engines index the site |
| `LICENSE` | All-Rights-Reserved terms for the public site |
| `.gitignore` | Keeps OS/editor/Python junk out of the repo |
| `.github/workflows/pages.yml` | Builds the reports index + deploys to Pages on every push |

## One-time setup (publish the site)
1. Create a **public** repo named **`mrktprice-site-public`** on GitHub.
2. Upload everything in this folder (drag the files into "Add file → Upload files", or `git push`).
3. Repo **Settings → Pages → Build and deployment → Source = GitHub Actions**.
4. Point the domain: at your registrar (GoDaddy/Namecheap) add four `A` records for `@`
   → `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`,
   and a `CNAME` for `www` → `<your-username>.github.io`.
5. Back in Settings → Pages, tick **Enforce HTTPS** once the domain check passes.

Done — **https://mrktprice.com** serves the dashboard, and **/reports/** serves Opportunity News.

## Add a new report
1. Copy `reports/report-template.html` → `reports/YYYY-MM-DD-short-slug.html`.
2. Edit the JSON metadata block at the top (title, date, summary, tags) and write the article.
3. Commit/upload it. The Pages workflow rebuilds the index and republishes automatically.
   *(Or run `python build_reports.py` locally first if you want to preview the list.)*

## Updating the dashboard
The nightly GitHub Actions workflow (`.github/workflows/pages.yml`) rebuilds the published data from
the in-repo engine under `tools/market_map/` and redeploys automatically; a push with `[rebuild]` (or
any change under `tools/market_map/`) regenerates `marketmap.json` and the terminal data in place.
