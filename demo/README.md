# Demo (step 8)

`demo_transcript.md` — human-readable Q&A transcript, the main article/
interview artifact.
`demo_results.json` — same data, structured (full chunk snippets included),
for programmatic reuse.

Regenerate with:
```
.venv/bin/python3 scripts/demo.py
```

## What this demonstrates

Five real questions against the Knowledge Base (24 TSB reports, 266
chunks), each returning a grounded, cited answer naming the specific
report(s) it came from — plus one deliberately ambiguous question run
twice: once showing a genuine retrieval failure, once showing the fix.

**The weak spot**: "What was the most recent incident in this dataset, and
what caused it?" Plain vector similarity search has no concept of
recency — it matches on semantic closeness to the query text, not on
actual dates. Run twice, it gave two different wrong answers (a 2019
report, then a 2018 report) — the corpus actually runs to January 2026.
Neither is remotely close, and the instability across runs is itself
informative: there's no "almost right" here, just semantically-plausible
noise.

**The fix**: not a better prompt or more retrieved chunks — structured
metadata. Each chunk was re-ingested with a `date_numeric` (YYYYMMDD
integer) attribute (`scripts/build_metadata_sidecars.py`), letting the
query be constrained with a real filter
(`{"greaterThan": {"key": "date_numeric", "value": 20260101}}`) instead of
relying on semantic similarity to a word like "recent". Filtered, it
correctly identifies the actual most recent report (R26Q0001, VIA Rail,
2026-01-12) every time.

This is the article's most important beat: it shows judgment about *when*
plain RAG retrieval breaks down and what class of fix actually applies
(structured filtering, not prompt tweaking), not just "I called an API."

## Generation model note

Uses **Amazon Nova Lite**, not an Anthropic Claude model. Partway through
this project, Bedrock started requiring a one-time "model use case
details" form submission for Anthropic models on this account — a new,
account-level gate unrelated to anything built here, and one that needs
the account owner's own business/use-case details to fill out. Rather than
block the demo on that, generation was switched to a Bedrock-native model
that was already unblocked. Retrieval quality (the actual "RAG" part) is
independent of which model does generation, so this doesn't affect the
project's findings at all — Titan Embeddings V2 (the model doing the real
work of retrieval) was never affected.
