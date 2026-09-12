# CLAUDE.md — rag-tsb-safety

This file seeds project context for Claude Code sessions working in this repo.
It is copied from Sections 2–4 of the original design brief
(`../../inputs/rag-tsb-project-brief.md`) — read that file for the full
decision trail (why this project exists, prioritization reasoning, handoff
notes) if deeper background is needed. This file carries forward only the
parts a session needs on every visit: dataset, technical approach, and
article framing.

## Workspace layout

This repo lives under a workspace root with three top-level folders:

```
ragproject/
├── inputs/                 Source material (the original design brief, TSB report exports, notes)
├── outputs/                Deliverables — manifest, article draft, diagrams. Not code.
└── code/rag-tsb-safety/    This repo
```

## Dataset — TSB Canada investigation reports

Chosen for storyline over generic public datasets: investigation reports have
built-in narrative drama ("here's what actually caused it, and how
investigators traced it back") and tie directly to two live/adjacent threads
in the author's job search: **CPKC** (railway) and the **energy/pipeline
sector** (Nutrien, Suncor, Trans Mountain). "I built a system to query
historical rail/pipeline safety investigations, with cited sources" is a real
conversation-starter with those employers, not just portfolio filler.

**Source:**
- Primary index: `https://www.tsb.gc.ca/eng/rapports-reports/rail/index.html`
  (rail) and the equivalent pipeline-mode index under
  `tsb.gc.ca/eng/rapports-reports/pipeline/` — sortable/filterable lists of
  individual investigation reports, each published as HTML and PDF, English
  and French.
- Reports are also individually mirrored on the Open Government Portal
  (`open.canada.ca/data`), one dataset entry per report.
- No confirmed bulk-download API — plan on scripted fetch of a curated list
  of report URLs, not a bulk archive pull.
- **Licensing — confirmed 2026-09-11.** TSB's own site (`tsb.gc.ca/eng/avis-notices/avis-notices.html`,
  "Ownership and use of content") is Crown copyright under the standard
  Government of Canada **non-commercial reproduction** terms — **not** the
  more permissive Open Government Licence – Canada that the open.canada.ca
  mirror defaults to. This does affect what's safe: reproduce/quote report
  text freely for non-commercial use provided you (1) exercise due diligence
  on accuracy, (2) cite the complete title and author (TSB) of the material
  reproduced, and (3) note that the reproduction is a copy of the version at
  the source URL. Commercial redistribution requires written permission from
  PWGSC. A personal, non-monetized portfolio article satisfies
  non-commercial use; give each cited excerpt an inline "Source: TSB report
  [ID], [URL]" attribution. Individual report pages carry no report-specific
  copyright notice beyond this site-wide policy (checked on R13D0054).
  Also worth an honest-boundary callout in the article: by statute (CTAISB
  Act 7(3)–7(4)) TSB findings assign no fault/liability and aren't binding
  in legal proceedings — the reports are safety analysis, not adjudication.
- **URL structure — confirmed 2026-09-11.** Each report has two related
  pages: an `/eng/enquetes-investigations/{mode}/{year}/{id}/{id}.html`
  overview page (occurrence summary, safety communications, recommendations)
  that links to an `/eng/rapports-reports/{mode}/{year}/{id}/{id}.html` full
  report page (the actual investigation report text — this is what
  ingestion should fetch). Older reports (pre-~2010) only have the
  `rapports-reports` page; the manifest's `url` column points at whichever
  page the index itself linked to, so check which pattern applies per row
  before scripting the ingestion fetch.

**Scope cut (keep it tactical):** don't ingest the full archive. Pick a
bounded, curated subset — 15–30 reports across rail + pipeline, weighted
toward more detailed/narrative-rich investigations (major occurrences tend to
have longer, more citable report text than minor-incident summaries) —
enough to demonstrate real retrieval quality and source attribution without
turning this into a data-engineering project.

## Technical approach

Standard managed-RAG shape — a minimal Bedrock Knowledge Base, not a
hand-built retrieval pipeline (that depth belongs to a separate, later
strategic "RAG from scratch" stage, not this build):

- **Ingestion:** curated report set (HTML/PDF) → S3 raw zone.
- **Bedrock Knowledge Base** (fully managed): handles chunking, embeddings
  (Titan Embeddings), and vector storage.
  - **Cost gotcha — check before provisioning:** Bedrock KB's default vector
    store (OpenSearch Serverless) has a standing minimum-capacity cost that
    accrues even at rest — classic weekend bill-shock. Check whether Amazon
    S3 Vectors is now a supported KB vector store (no idle cost) before
    defaulting to OpenSearch Serverless. Otherwise, tear the vector store
    down immediately after the demo/article is captured.
- **Query/generation:** Bedrock Converse API against the Knowledge Base, with
  source attribution surfaced in every answer — this is the single most
  important thing to demo well, since "which report did this answer come
  from" is the credibility signal that makes RAG different from an
  ungrounded chat response.
- **Demo/eval:** a short script or notebook asking real questions ("what
  type of track defects caused the most incidents in this set," "what
  corrective actions were recommended after X") and showing grounded, cited
  answers — this is the artifact worth screenshotting for the article and
  for interview show-and-tell.
- **Cost governance:** a small, disclosed cost cap/estimate for the build,
  stated plainly in the article. Same discipline as this author's other
  portfolio projects (camera project, K8s series) — never leave metered
  infrastructure running unmetered.

## Storyline / article framing

One teaching article (tactical scope — not a multi-stage series): working
angle **"What actually caused it — building my first RAG pipeline over
Canada's rail and pipeline safety investigations."**

Beats:
1. The hook — root-cause investigation reports as a naturally RAG-shaped
   corpus (long, technical, citation-heavy documents where grounding and
   source attribution matter more than in most demo corpora).
2. Why RAG, not fine-tuning or SageMaker — the **MLOps vs. AIOps vs. LLMOps**
   aside: name explicitly why this is neither of the other two.
3. The build — Knowledge Base architecture, the scoped report subset,
   chunking/retrieval behavior observed.
4. The demo — real questions, real cited answers, at least one example where
   retrieval quality mattered (a case where a badly-chunked or ambiguous
   query returned a weaker/less-grounded answer, and what fixed it) — this
   is the detail that shows judgment, not just "I called an API."
5. Honest boundary — explicitly state what this doesn't prove: not
   enterprise-scale, not multi-tenant, not agentic, not fine-tuned.
6. Close — cost receipt, and a one-line pointer to what's next.

## Reporting back

Once built, the deliverable the job-search project cares about is the
**published article link** and a one-line "have built" claim — not the code
itself. Report the published link back so it can fold into
`materials-to-strengthen.md` and any live resume/cover letter.
