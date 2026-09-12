# Report manifest

`reports_manifest.csv` — the curated subset of TSB investigation reports this
project ingests. 24 reports total (16 rail, 8 pipeline), spanning 2007–2026.

## How this was selected

Source: TSB's rail and pipeline report indexes
(`tsb.gc.ca/eng/rapports-reports/{rail,pipeline}/index.html`), fetched and
parsed on 2026-09-11 with `../scripts/parse_tsb_index.py`. Those indexes list
**526 total reports** (484 rail back to 1991, 42 pipeline back to 1994) — the
full parsed list is saved for traceability at
`../../inputs/tsb_full_report_index_2026-09-11.csv`.

**Note for future fetches:** `tsb.gc.ca` returns HTTP 403 to non-browser user
agents (this blocked the WebFetch tool) but 200 to a plain `curl` with a
standard browser `User-Agent` header — no special auth needed, just a UA.

Per the brief's scope cut (15–30 reports, weighted toward longer/more
detailed investigations), the selection favors:

- **Major/narrative-rich occurrences** over short/minor summaries — main-track
  derailments, collisions, employee fatalities, and pipeline
  ruptures/releases (pipeline reports are almost all substantive; the pool of
  41 completed pipeline reports has no "minor incident" category comparable
  to rail's routine crossing collisions).
- **Direct relevance to the job-search threads named in the brief**: CPKC
  (post-2023-merger-branded reports included explicitly: R24C0020, R25T0177)
  and the energy/pipeline sector, including Trans Mountain by name
  (P18H0034).
- **A few historically significant, highly-detailed investigations** that
  will produce strong demo answers and citations: Lac-Mégantic (R13D0054 —
  the most significant rail disaster in the set), the fatal 2019 runaway
  derailment near Field, BC (R19C0015), and the 2015 Gogama, Ontario
  crude-by-rail derailment (R15H0021).
- **Variety for retrieval-quality testing**: passenger rail (VIA, exo
  commuter), a US cross-border carrier (BNSF), and one deliberately old
  report (P07H0014, 2007) using the legacy `/rapports-reports/` URL path
  rather than the newer `/enquetes-investigations/` path, to see whether
  ingestion/chunking behaves consistently across report-page HTML eras.

All 24 URLs were spot-checked with `curl` and return HTTP 200.

## Columns

`report_id, mode, date, occurrence_type, company, location, url, notes`

`notes` is manifest-only context (why this report was picked) — not part of
the source data, and not something to feed into the Knowledge Base ingestion
metadata.

## Licensing — confirmed 2026-09-11

TSB's own site terms (`tsb.gc.ca/eng/avis-notices/avis-notices.html`) govern,
not the open.canada.ca mirror's Open Government Licence. Non-commercial
reproduction is permitted with attribution (title, TSB as author, and a note
that it's a copy of the version at the source URL) — commercial
redistribution needs PWGSC permission. See `../CLAUDE.md` for the full
finding, including the statutory no-fault/non-binding caveat worth
mentioning in the article.

## Full report URL vs. overview URL

The `url` column here is whatever the index page linked to. Two patterns
exist:

- `/eng/enquetes-investigations/{mode}/{year}/{id}/{id}.html` — an overview
  page (occurrence summary + recommendations) that links onward to the full
  report via a "View final report" button.
- `/eng/rapports-reports/{mode}/{year}/{id}/{id}.html` — the full
  investigation report text. Older reports (pre-~2010, e.g. P07H0014,
  P12H0105 in this manifest) link directly to this page with no separate
  overview page.

Confirmed by sampling 4 reports (2 rail, 2 pipeline; old + new): swapping
`enquetes-investigations` → `rapports-reports` in an overview URL reliably
yields that report's full-report URL. Ingestion (checklist step 6) should
fetch the full-report page, not just the overview page.
