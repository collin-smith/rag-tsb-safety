# A tool-routing agent, and two real failures found building it

`scripts/agent_router.py` gives Nova Lite two tools over Bedrock Converse's
native tool use (`toolConfig`) -- `aggregate_structured_findings` (exact
counts over the extraction table from `extract_structured_findings.py`) and
`verified_semantic_query` (the citation-gated RAG path from `rag_utils.py`)
-- and lets the model decide which one a question needs, instead of a human
picking the right script. This is the deliberate difference from the
extraction pass: that script is a fixed loop; this one routes itself.

## What worked

| Question | Tool(s) called | Correct? |
|---|---|---|
| "How many reports cite an unimplemented prior recommendation, broken down by mode?" | `aggregate_structured_findings` | Yes -- exact counts (22 total, matches the extraction pass) |
| "What fraction of pipeline reports involved dangerous goods?" | `aggregate_structured_findings` (chained twice: total, then dangerous-goods count) | Yes -- correctly decomposed a fraction into two lookups and did the division itself |

Both are the target behavior: no hallucinated count, no semantic-search
guess at "how many" -- the model chose the tool built for exact aggregation
and used it correctly, including a two-step chain it wasn't explicitly told
to perform.

## Failure 1: a reproducible Nova Lite tool-use decoding bug on one specific phrase

"What caused the Lac-Megantic derailment?" broke tool-use decoding
consistently at temperature 0, in two different visible forms:

- A hard `ModelErrorException`: *"Model produced invalid sequence as part of
  ToolUse."*
- A silent degeneration: the model's `<thinking>` block correctly states
  intent to call `verified_semantic_query`, then emits nothing but blank
  lines until it hits the token cap -- no tool call ever produced.

**Isolated and confirmed reproducible**: a structurally identical question
about a different report ("What caused the Gogama derailment?") worked
cleanly on the first try. A temperature bump to 0.3 (the standard fix for a
stochastic decoding fluke) did *not* resolve it -- both attempts degenerated
identically, meaning this isn't sampling noise, it's deterministic given
this token sequence and this tool schema.

**Practical fix, not a full root-cause fix**: added a bounded retry (one
extra attempt at temperature 0.3) and, if that also stalls, an
orchestration-level fallback -- detect that no tool was ever successfully
called and the model's own text is empty filler, then default to calling
`verified_semantic_query` directly with the raw question rather than
surfacing garbage. This is the same principle as the citation-integrity gate
applied one layer up: when the routing layer itself is unreliable, fail
safe into the grounded path instead of returning whatever the model
produced.

## Failure 2 (found via the fallback): grounded citations that cite the wrong report

Once the fallback path fired, `verified_semantic_query` returned a
fluent, **non-empty-citation** answer for "What caused the Lac-Megantic
derailment?" -- correctly passing the existing citation gate -- but the
content and the cited report ID (`R19C0015`, the Yoho/Field BC runaway) were
for the **wrong incident**. The actual Lac-Mégantic report is `R13D0054`.

This is a materially different, and worse, failure than the ones already
documented in `insight_exploration.md`. Those were **empty**-citation
failures: the answer was ungrounded and the citation count immediately
exposed it. This one has a **real, non-empty citation to a real report** --
it just isn't the report the question was actually about. `len(citations) >
0` is necessary but not sufficient; it confirms the answer is grounded in
*something* in the corpus, not that it's grounded in the *right* thing.

Checked directly to rule out a simple explanation: a plain `retrieve` call
(no generation) with the identical unaccented phrasing and mode filter
correctly returns `R13D0054` as the top match, and an accented version
("Lac-Mégantic") also returns `R13D0054` cleanly -- so it isn't an
accent/tokenization issue in the query text itself. The mismatch happened
specifically inside the managed `retrieve_and_generate` call path (different
internal retrieval than a plain `retrieve`, and it pulls more chunks --
`numberOfResults: 8` here vs. 3 in the isolated check), and Nova Lite's
generation step apparently weighted or attributed content from a
co-retrieved brake-failure chunk in `R19C0015` over the correct source.
Root cause not fully isolated -- worth stating plainly rather than
over-claiming a fix that wasn't built.

**What this means, honestly stated**: for the one report in this entire
corpus most likely to appear in an executive-facing demo -- the flagship,
best-known incident -- this pipeline can silently misattribute the answer
while looking fully grounded. The operational rule from `insight_exploration.md`
("never trust an answer without checking citations are non-empty") is
necessary but not sufficient on its own. A stronger rule this project should
adopt going forward, not yet built: **when a question names an identifiable
entity (a place, a report ID, a company), verify the cited report_id
actually matches that entity before trusting the answer** -- a cheap,
deterministic check, distinct from the semantic retrieval it would be
checking.

## Cost

Full agent-router build, including all diagnostic isolation calls (the
error reproduction, the temperature-bump test, the three retrieval-only
checks that ruled out the accent explanation): well under 5 cents. The three
demo questions above alone: **$0.0005** measured (Nova Lite: $0.06/M input,
$0.24/M output tokens). Diagnostic-only calls (mostly small, single-turn,
capped at 300-1500 tokens) added a few thousand additional tokens at the
same rate -- total for this entire exercise stayed under $0.01.
