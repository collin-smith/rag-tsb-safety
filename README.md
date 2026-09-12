# rag-tsb-safety

A portfolio project demonstrating a managed RAG pipeline over Canada's rail
and pipeline safety investigation reports (Transportation Safety Board of
Canada, tsb.gc.ca):

**Curated report subset → S3 → Bedrock Knowledge Base (Titan Embeddings) → Bedrock Converse retrieve-and-generate demo, with cited answers**

Built to close a specific hands-on gap: no prior hands-on RAG pipeline
experience (prior AWS AI work was Bedrock Converse without a retrieval step,
plus classical Glue ETL). Scoped as a weekend tactical build, not the full
strategic AI Hands-On Series.

## Workspace layout

This repo lives under a workspace root with three top-level folders:

```
ragproject/
├── inputs/                 Source material — design brief, TSB report exports, notes
├── outputs/                Deliverables — manifest, article draft, diagrams. Not code.
└── code/rag-tsb-safety/    This repo
```

## Status

Project shell only — see `CLAUDE.md` for the full design brief (dataset,
technical approach, article framing) and the kickoff checklist in
`../../inputs/rag-tsb-project-brief.md` Section 6 for the step-by-step build
order.

## Decisions

- **Dataset:** 15–30 TSB rail + pipeline investigation reports, weighted
  toward longer/more detailed investigations. Manifest tracked as the first
  build artifact.
- **Vector store:** default to whichever Bedrock KB vector-store option has
  no idle cost (check Amazon S3 Vectors support before defaulting to
  OpenSearch Serverless, which bills a standing minimum even at rest).
  Otherwise tear down immediately after the demo is captured.
- **Scope:** managed Bedrock Knowledge Base, not a hand-built retrieval
  pipeline. That depth is a separate, later "RAG from scratch" project.
