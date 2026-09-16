# Using the RAG system to explore the corpus itself

Beyond the core demo (`demo_transcript.md`), these queries test what the
system can honestly tell you *about* the 24-report dataset — thematic
synthesis across documents, not just single-report lookups. Same KB
(`LVBYRHRW4C`), same generation model (Amazon Nova Lite).

## What worked: thematic synthesis

**Q: Are there safety recommendations TSB has made more than once across
different investigations, suggesting a recurring unresolved issue?**

> Yes... recommendations related to physical fail-safe train controls,
> safety management systems, and hazard identification and risk
> assessment... made in multiple investigations, indicating these issues
> have not been fully resolved.

Drawn from 6 distinct reports (`R23V0205`, `R22C0065`, `R15H0021`,
`R15T0173`, `R17W0267`, `R25T0189`) — genuine cross-document synthesis,
and a real, useful finding: TSB repeats itself because the underlying
systemic issues repeat.

**Q: How do the root causes of the pipeline incidents compare to the rail
incidents?**

> Pipeline: manufacturing defects, inadequate inspection/maintenance,
> human error in data analysis... Rail: maintenance practices, human
> error, inadequate training...

Reasonable, specific, correctly attributed to real reports on each side
(`R15H0021` rail, `P24H0018`/`P14H0011` pipeline).

## What it got wrong: mode coverage

**Q: What common human-factors or organizational themes appear across
these rail and pipeline investigations?**

The question explicitly asked about *both* modes. The answer drew from
**two pipeline reports only** (`P24H0018`, `P18H0034`) — it never
retrieved a single rail report, despite 16 of the 24 documents being rail
investigations. The retrieved chunks happened to match the query's
"human factors / organizational" phrasing more closely on the pipeline
side; nothing in plain vector search enforces balanced coverage across a
corpus. The answer reads as complete. It isn't.

## What it can't do reliably: counting

**Q: How many of the reports in this dataset involved a fatality?**

> Based on the retrieved results, 4 of the reports in this dataset
> involved a fatality.

Reports drawn from `R19T0147`, `R19C0015`, `R21D0001`, `R18M0037` — four
of the eight chunks retrieved for this query happened to be from
fatality-related reports, so the model reported "4" as if it were a total
count. The manifest's actual fatality-related reports include at least
`R21D0001`, `R19T0147`, `R18M0037`, `R17W0267`, and the Lac-Mégantic
disaster (`R13D0054`, 47 fatalities) — five or more of 24, and that's
before considering that R19C0015 alone involved three fatalities, not one
"instance." The model wasn't hedging or uncertain; it stated a specific
number with full confidence, drawn from a partial retrieval it had no way
to know was partial.

(Nova Lite's raw output also leaked an internal scaffolding artifact ahead
of the answer here — `Action: GlobalDataSource.search(query="...")` — a
model-specific formatting quirk, not a retrieval issue, but worth noting
if switching generation models later.)

## Business/safety insights (a second pass, aimed more deliberately at value)

**Q: What track/infrastructure conditions most commonly contributed to
derailments, and what maintenance practice would address them?**

> Degraded track conditions — contaminated/worn ballast, lifted spikes,
> rail creep, missing/loose anchoring, skewed/worn/plate-cut ties...
> regular proactive maintenance, including ballast cleaning, rail joint
> maintenance, tie replacement, and managing rail neutral temperature to
> prevent buckling.

Concrete and actionable — a real maintenance-planning takeaway, correctly
attributed (`R22C0065`).

**Q: What role did dangerous-goods transport play in outcome severity, and
what does that say about crude-by-rail risk concentration?**

> ...the 50 mph speed restriction in place at the time "would not reduce
> the severity of a derailment" and is "not sufficient for unit trains
> transporting Class 3 flammable liquids"... more stringent safety
> measures, such as lower speed restrictions and improved tank car design,
> are necessary.

Drawn from Lac-Mégantic and Gogama (`R13D0054`, `R15H0021`) — a genuinely
useful, specific safety-policy insight, not a generic statement, and
directly relevant to any crude-by-rail conversation (energy sector,
CPKC).

**Q: Did any investigation find a previous safety recommendation, if
acted on, could have prevented the occurrence?**

> ...Transport Canada had previously recommended railways implement
> additional backup safety defences... this recommendation had not been
> fully implemented, and the lack of physical fail-safe train controls in
> signalled territory contributed to the occurrence.

From `R23V0205` — this is the strongest business insight in the set: a
known, previously-flagged risk, not fully acted on, contributing to a
*later* incident. That's a real "cost of inaction" narrative, not a
platitude.

## The most important finding: an empty citation is not a soft failure

**Q: What gaps in safety management systems or risk assessment processes
did TSB identify, separate from the immediate mechanical or human
cause?**

The generated answer was detailed, specific, well-organized, and
completely plausible — five numbered SMS/risk-assessment gaps, citing
specifics like "the Red Book" and TDG training requirements. It reads
exactly like the other grounded answers in this document.

**`retrievedReferences` for this answer: empty. Zero.** Reproduced twice.
Bedrock's own API returned a citations block with no supporting chunks at
all, meaning this specific answer is not actually anchored to anything in
the 24-report corpus — it's the model generating a plausible-sounding
synthesis from its own training knowledge about rail safety investigations
in general, not from *this* dataset.

This is the single most important finding in this whole exercise, more
important than the temporal-query or coverage-gap failures above, because
it's a **citation-integrity** failure, not a retrieval-quality one: the
API's response shape looks identical whether an answer is grounded or not
unless you specifically check whether `retrievedReferences` is non-empty.
A consumer who trusts fluent, confident prose — which is exactly what
every other answer in this project looks like — would have no way to
tell this one apart from a real, cited finding without checking.

**The operational rule this produces**: never surface a
`retrieve_and_generate` answer as "grounded" without asserting
`len(citations[*].retrievedReferences) > 0` first. An empty citation list
should be treated as a hard failure state — refuse the answer or fall back
to "no supporting evidence found" — not silently accepted because the
prose still reads well.

**A second, more revealing example of the same failure.** Asked what
early-warning precursors appeared across these investigations, the model
again returned zero citations — but this time named a real report by
detail: "the Nig Creek pipeline's integrity management program did not
consider cracks... significant hazard." Nig Creek is genuinely in this
corpus (`P12H0105`). The model wasn't retrieving it for this query,
though — it was recalling it from pretraining, because TSB reports are
public web content a foundation model may have seen during training. That
makes this failure mode worse than a generic hallucination: an ungrounded
answer can be specific and even factually accurate about a report in your
own corpus, purely by coincidence of what the base model already knew,
with zero connection to *your* retrieval pipeline. Citation-count
verification is the only way to tell the difference — reading the prose
cannot.

## The coverage gap, confirmed at scale, and fixed the same way as before

The "government safety summary" drafted from this exploration (5 points,
6 cited reports) turned out to be **100% rail — zero pipeline**, despite
8 of the 24 reports being pipeline investigations, including Trans
Mountain. Same root cause as the earlier rail-vs-pipeline coverage gap
above, just showing up systematically across a whole set of policy
questions instead of one: rail is twice the corpus (16 vs 8 reports), so
plain top-k semantic search skews toward it by default on mode-neutral
questions.

The fix is the same pattern as the `date_numeric` filter that fixed the
temporal weak spot: don't hope semantic similarity happens to include the
underrepresented category — force it with a metadata filter.
`build_metadata_sidecars.py` already attaches a `mode` (`rail`/`pipeline`)
attribute to every chunk, so:

```python
retrievalConfiguration={
    "vectorSearchConfiguration": {
        "numberOfResults": 8,
        "filter": {"equals": {"key": "mode", "value": "pipeline"}},
    }
}
```

Filtered to pipeline only, one question came back genuinely grounded (9
citations, `P17H0011`, `P13H0107`, `P24H0018`) — and, notably, the model
*hedged appropriately* rather than confabulating: "TSB did not explicitly
recommend regulatory or industry practice changes in the provided search
results," before summarizing what the retrieved text actually supported
(cross-border crossing-agreement clarity, in-line-inspection data-review
rigor, ground-disturbance procedures). That calibration — saying "not
explicitly stated" instead of inventing a confident answer — is exactly
what you want from a grounded response, and it's a useful contrast to
what happened next.

**A third empty-citation hallucination, and a pattern worth naming.** The
other pipeline-filtered question came back with **zero citations again**,
and named "the Nig Creek pipeline" (`P12H0105`, real) with specific,
plausible detail about its integrity management program. This is the
second time this exact report surfaced this way. It's specific enough,
and repeats often enough, to suggest Nig Creek's TSB report is
well-represented in whatever the base model was trained on — meaning the
model has a genuine, specific memory of it that has nothing to do with
this project's retrieval pipeline, and will keep surfacing convincingly
regardless of what's actually indexed. Citation-count verification isn't
a one-time check; it has to run on every single answer.

## Cross-modal human-factors synthesis (57-report corpus, all 4 modes)

Same question, asked separately per mode with a `mode` filter (not one
unfiltered query across all four — that would just repeat the coverage-gap
failure at a larger scale), each answer checked for non-empty citations
before being trusted:

| Mode | Dominant human/organizational factor (verified) | Reports |
|---|---|---|
| Rail | Inadequate communication/coordination between crew members — inexperience, divided attention from competing radio calls | `R23V0205`, `R17W0267`, `R24C0020` |
| Pipeline | Inadequate training + human performance variability in interpreting in-line inspection data — a real crack downgraded to "non-reportable" with the rationale undocumented | `P24H0018` |
| Marine | Fatigue — specifically named as "widespread in the commercial fishing industry," reducing the ability to recognize and respond to an unfolding emergency | `M20P0229`, `M23C0257` |
| Aviation | Loss of situational awareness (attentional narrowing, spatial disorientation, degraded visual environments) | `A19C0145`, `A19O0178`, `A19Q0128` |

**The story this tells:** there is no single "human factors" narrative that
applies across transportation modes — the failure shape follows the
*operational structure* of the mode, not a generic safety-culture platitude.
Rail and pipeline failures center on **coordination between multiple
people** (a crew, an inspection review committee) where information didn't
transfer cleanly. Marine and aviation, in this corpus, center on **a single
person's degraded cognitive state** (a fatigued fishing-vessel master, a
solo pilot losing situational awareness) — because that's literally the
operating structure: small-crew commercial fishing and single-pilot general
aviation, not airline-scale multi-crew operations. A regulator overseeing
all four modes is uniquely positioned to see this — an individual company
in just one sector would only ever see its own slice and might reasonably
assume "communication training" or "fatigue management" is the universal
fix, when the data says the right intervention actually depends on how many
people are in the loop when the decision gets made.

**The methodological point worth keeping, too:** aviation's first answer
came back ungrounded (0 citations) on a question framed around "crew
communication breakdown" — because that framing assumes multi-crew
operations, and this project's curated aviation subset is mostly
single-pilot general aviation. Rephrased around solo-pilot factors
(situational awareness, spatial disorientation), it grounded immediately
with real citations. The lesson generalizes past aviation: a retrieval
failure isn't always a system bug — sometimes the question just doesn't
match what's actually in the corpus, and the fix is understanding your
corpus's composition, not just tuning the retrieval pipeline.

## The takeaway

Plain RAG retrieval (top-k over a vector index, no aggregation step) is
genuinely good at "find the specific fact and cite it" and "synthesize a
theme across whichever documents get retrieved." It is not built for
"count every instance of X in the corpus" or "guarantee balanced coverage
across categories" — those need a different mechanism entirely (a
structured query over metadata, or an agentic loop that explicitly
iterates the full document list), not a bigger `numberOfResults` or a
better prompt. This is the same lesson as the temporal-query weak spot in
`demo_transcript.md`, generalized: know which questions are semantic
(RAG handles them well) and which are structured/exhaustive (RAG will
answer confidently and wrongly).
