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
  - **Cost gotcha — resolved 2026-09-11.** Confirmed via `aws bedrock-agent
    create-knowledge-base help` and a live `aws s3vectors list-vector-buckets`
    call in this account/region (us-east-1): **`S3_VECTORS` is a supported
    Knowledge Base storage-configuration type**, alongside
    `OPENSEARCH_SERVERLESS`. S3 Vectors has no standing/idle capacity cost
    (pay per vector stored + per query) — use it instead of OpenSearch
    Serverless (which bills a minimum OCU baseline even at rest) and there's
    no weekend-bill-shock risk to manage in the first place. No need to plan
    an urgent teardown of the vector store specifically; still tear down
    everything not needed for future demos per step 10.
- **Region — migrated to `ca-central-1` 2026-09-16, data residency.**
  TSB is a Canadian federal body; the build originally ran in `us-east-1`.
  Both halves of the residency gap are now closed: Titan Embeddings V2
  supports on-demand invocation directly in `ca-central-1`, and Amazon
  Nova Lite now has a genuine all-Canada geographic inference profile
  (`ca.amazon.nova-lite-v1:0`, shipped 2025-09-25 — routes to
  `ca-central-1`/`ca-west-1` only, not the US/Global routing it had when
  this file was first written). Verified independently via CloudTrail
  (`awsRegion: ca-central-1` on every call). `us-east-1` resources torn
  down after migration; see `infra/README.md`'s migration section for the
  full account of what was checked and how.
- **Query/generation:** explicit `retrieve()` + `converse()` calls
  (`rag_utils.verified_retrieve_and_generate`), **not** Bedrock's
  `retrieve_and_generate` convenience API — retired 2026-09-16 after it
  was found to silently disconnect from the KB's own `retrieve()` results
  on the `ca-central-1` KB specifically (see `rag_utils.py`'s docstring
  for the full isolation process). Source attribution surfaced in every
  answer is still the single most important thing to demo well, since
  "which report did this answer come from" is the credibility signal that
  makes RAG different from an ungrounded chat response — this bug was a
  sharper version of exactly that concern, not a side issue.
  - **Generation model — Amazon Nova Lite, not Claude, decided 2026-09-12.**
    Bedrock started requiring a one-time "model use case details" form for
    Anthropic models on this account partway through the build (a new,
    account-level gate — even a previously-working direct Converse call to
    Claude Haiku started failing the same way). That form needs the account
    owner's own business/use-case details, so rather than block on it or
    fill it out with guessed content, generation uses Nova Lite instead —
    already unblocked, and retrieval quality (the actual RAG mechanism)
    doesn't depend on which model does generation.
- **Demo/eval — built 2026-09-12, see `demo/`.** `scripts/demo.py` asks 5
  real questions (including CPKC- and Trans Mountain-specific ones tied to
  the job-search threads) plus one deliberately ambiguous query run twice
  (unfiltered, then fixed). See `demo/README.md` for the full writeup — in
  short: plain vector similarity has no concept of recency, so "what was
  the most recent incident" returned a different wrong (old) report on
  each unfiltered run; adding a `date_numeric` metadata attribute at
  ingestion (`scripts/build_metadata_sidecars.py`) and filtering on it
  fixed it reliably. This is the strongest article beat 4 candidate.
- **Cost governance:** a small, disclosed cost cap/estimate for the build,
  stated plainly in the article. Same discipline as this author's other
  portfolio projects (camera project, K8s series) — never leave metered
  infrastructure running unmetered.

## Storyline / article framing

**Decided 2026-09-12: two staged articles**, not one combined piece —
matching the EKS GitOps series' per-stage format, and leaving room for an
optional future "Stage 3 — agentic" if that's ever pursued (not committed).
Working angle **"What actually caused it — building my first RAG pipeline
over Canada's rail and pipeline safety investigations."**

- **Stage 1 — The Corpus & the Question**: dataset selection rationale,
  the licensing discovery (Crown copyright vs. the more permissive Open
  Government Licence), ingestion. ~700–900 words — thinner on its own, but
  the licensing angle can carry it as a standalone hook.
- **Stage 2 — The Pipeline**: Knowledge Base + S3 Vectors (including the
  cost-gotcha avoidance and the real ingestion debugging saga — a
  non-filterable-metadata bug, not the throttling it first looked like),
  the demo, the weak-spot-then-fix beat, honest boundaries, cost receipt.
  ~1,400–1,800 words — the real meat.

Beats below map roughly 1–2 to Stage 1, 3–6 to Stage 2.

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
