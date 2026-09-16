# rag-tsb-safety

A portfolio project demonstrating a managed RAG-to-agent pipeline, built end
to end and debugged honestly, over Canada's rail, pipeline, marine, and
aviation safety investigation reports (Transportation Safety Board of
Canada, tsb.gc.ca):

**370-document corpus (S3) → Bedrock Knowledge Base + S3 Vectors (Titan Embeddings) → explicit `retrieve()` + `converse()` (Amazon Nova Lite) → Bedrock Guardrails (grounding check, PII, denied topics) → tool-calling agent over structured findings**

Built to close a specific hands-on gap: no prior hands-on RAG pipeline
experience (prior AWS AI work was Bedrock Converse without a retrieval step,
plus classical Glue ETL). Written up as a 6-phase article series (see
`../../outputs/rag-tsb-safety/articles/`) — not a single write-up, because
each phase found something real enough to warrant its own honest accounting:
a licensing discovery, an ingestion bug, a data-residency migration, a
security-testing result, and one AWS-service inconsistency that isn't
publicly documented anywhere else.

## What's actually in this repo

- `scripts/` — ingestion (`ingest_reports.py`), the core retrieve+generate
  helper (`rag_utils.py`), the demo (`demo.py`), a tool-calling agent that
  routes between exact aggregation and semantic search (`agent_router.py`),
  exhaustive structured extraction (`extract_structured_findings.py`), and
  the population-scale validation pipeline used to statistically check the
  curated corpus's headline finding (`build_validation_sample.py` /
  `run_validation_ingest.py` / `run_validation_extraction.py`).
- `infra/` — the CloudFormation template and IAM policies for the Knowledge
  Base + S3 Vectors stack, plus a detailed `README.md` covering every real
  infrastructure decision and bug hit along the way (a CloudFormation
  early-validation failure that was never fully explained, a Titan
  Embeddings quota throttling red herring, the actual root-cause bug, and
  the `ca-central-1` data-residency migration).
- `manifest/` — the curated 57-report subset (selection rationale in
  `manifest/README.md`) plus the marine/aviation expansion used for the
  313-report statistical validation sample.
- `demo/` — captured transcripts and structured findings from the demo,
  the agent, and the exhaustive extraction pass.

## Architecture, as it actually stands today

Not the original design — the current, migrated, bug-fixed state:

- **Region: `ca-central-1`**, migrated from `us-east-1` for data residency
  (TSB is a Canadian federal body). Both embedding (Titan V2, on-demand)
  and generation (Nova Lite via the `ca.amazon.nova-lite-v1:0` geographic
  inference profile) stay in-region — verified independently via
  CloudTrail, not just self-reported.
- **Vector store: Amazon S3 Vectors**, chosen over the default OpenSearch
  Serverless specifically because it carries no idle-capacity cost.
- **Generation path: explicit `retrieve()` + `converse()`, not Bedrock's
  `retrieve_and_generate` convenience API.** That API was found to
  silently disconnect from the Knowledge Base's own `retrieve()` results
  on this region's KB — a real, reproducible bug, isolated and documented
  in `scripts/rag_utils.py`'s module docstring and `infra/README.md`.
- **Bedrock Guardrails**, prototyped and tested (not yet wired into the
  production query path) — a contextual grounding check tested directly
  against the bug above, a denied-topic policy, and Canada-specific PII
  anonymization.

## Status

Built through the full 6-phase arc described in the article series. Live
in the account right now: the `ca-central-1` Knowledge Base, S3 Vectors
store, and the Guardrails prototype — kept running for demo/interview
purposes, not yet torn down (see `infra/README.md`'s teardown section for
the exact commands when that's ready). `us-east-1` has been fully
decommissioned.

## Decisions worth knowing before reading the code

- **Dataset:** 57 curated rail/pipeline/marine/aviation reports (weighted
  toward longer, more consequential investigations) plus a 313-report
  stratified random sample used to validate the curated corpus's headline
  finding at population scale — full rationale in `manifest/README.md`.
- **Vector store:** Amazon S3 Vectors, checked live against
  OpenSearch Serverless's standing idle cost before choosing.
- **Scope:** a managed Bedrock Knowledge Base, not a hand-built retrieval
  pipeline — that depth is a separate, later "RAG from scratch" project.
- **Generation model:** Amazon Nova Lite, not an Anthropic model — Bedrock
  started requiring a one-time account-level "model use case" form for
  Anthropic models partway through this build; rather than block on it,
  generation moved to an already-unblocked model. Retrieval quality is
  independent of which model does generation.
