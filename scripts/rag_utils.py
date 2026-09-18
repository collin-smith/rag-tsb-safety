"""Shared grounding-verification helpers for the rag-tsb-safety project.

Built from a real failure found in demo/insight_exploration.md: Bedrock's
`retrieve_and_generate` can return a fluent, well-cited-looking answer with
an EMPTY `retrievedReferences` list -- meaning the model answered from its
own pretraining (TSB reports are public web content), not from this
project's Knowledge Base, and the response shape gives no visual signal
that this happened. Confirmed twice, reproducibly, in that exploration.

The rule this module enforces: never treat a retrieve_and_generate (or a
retrieve-then-generate) answer as grounded without asserting citations/
retrieved chunks are non-empty first. An empty result is a hard failure
state, not a soft one -- callers get `grounded=False` and must decide
whether to discard, retry, or surface the gap explicitly, never silently
accept fluent prose as evidence.

**2026-09-16, ca-central-1 migration: a second, worse version of that same
failure mode.** Bedrock's `retrieve_and_generate` convenience API was found
to silently disconnect from the KB's own `retrieve()` results on this
region's Knowledge Base -- confirmed via a same-instant paired comparison
(retrieve() ranked the correct report #1 by a clear margin;
retrieve_and_generate()'s internal citations never included it, across
repeated runs, at numberOfResults 5/10/20, on a fully-settled 370-document
corpus). Ruled out: generation-model behavior (a fixed-context test showed
both the on-demand and inference-profile paths generate correctly from
identical evidence), and corpus churn (persisted after ingestion fully
completed). Not reproduced on the equivalent us-east-1 KB with the same
query. Root cause not isolated beyond that -- looks like a Bedrock-side
inconsistency between retrieve_and_generate's internal retrieval and the
KB's own retrieve() API, specific to this region/KB. Worked around by
retiring `retrieve_and_generate` entirely: this function now calls
`retrieve()` and `converse()` as two explicit, separately-inspectable
steps, so citations are guaranteed to reflect what was actually retrieved
and passed to the model.

**2026-09-17: the Phase 6 Guardrail wired in for real.** Phase 6 tested
`rag-tsb-safety-guardrail` (`ca-central-1`, id `ee95ld5r9ckp`, published
version `1`) standalone via `ApplyGuardrail` and found two things worth
carrying into this function rather than leaving as isolated test results:
(1) the contextual grounding check catches a wrong-document answer
inconsistently -- it tracks how tightly the wrong answer paraphrases the
wrong source, not whether the right document was retrieved, so it is a
second, independent check on top of getting retrieval right, never a
substitute for it; (2) a qualified `query` block (the tag the grounding
check needs) suppresses topic-policy evaluation on that same call, so a
single `ApplyGuardrail` call reusing qualified blocks for everything would
silently skip content moderation on exactly the turns where it matters.
The fix carried over verbatim from Phase 6: two calls, not one -- an
unqualified gate on the raw question *before* `retrieve()` runs (can
short-circuit the whole pipeline on a denied-topic hit without ever
calling `retrieve()` or the model), and a qualified grounding/relevance
check on the retrieval + answer *after* generation. `guardrail_id` is
optional here (`None` skips both calls) so `retrieve_all_chunks`-style
exhaustive-extraction callers that never ran this pattern aren't forced
into it, but every caller that wants the Phase 6 finding to mean something
in production, not just in Phase 6's own isolated tests, should pass it.
"""
import json


def _apply_input_guardrail(runtime_client, guardrail_id, guardrail_version, question_text):
    """Gates the raw question before retrieve() runs.

    Deliberately unqualified content (no `query`/`grounding_source` tag) --
    a qualified block suppresses topic-policy evaluation on that same call
    (Phase 6's operational-gotcha finding), so the denied-topic and content
    filters only actually fire here, on the plain question.
    """
    response = runtime_client.apply_guardrail(
        guardrailIdentifier=guardrail_id,
        guardrailVersion=guardrail_version,
        source="INPUT",
        content=[{"text": {"text": question_text}}],
    )
    intervened = response.get("action") == "GUARDRAIL_INTERVENED"
    message = None
    if intervened:
        outputs = response.get("outputs", [])
        message = outputs[0]["text"] if outputs else "Question blocked by guardrail policy."
    return intervened, message


def _apply_output_guardrail(runtime_client, guardrail_id, guardrail_version,
                             context_text, question_text, answer_text):
    """Checks the retrieval + generated answer after the fact.

    Qualified blocks (`grounding_source` / `query` / `guard_content`) --
    the shape the contextual grounding check needs. Phase 6 found this
    catches a wrong-document answer inconsistently, tracking how tightly
    the wrong answer paraphrases the wrong source rather than whether the
    right document was retrieved -- a second, independent check on top of
    citation non-emptiness, not a substitute for it.
    """
    response = runtime_client.apply_guardrail(
        guardrailIdentifier=guardrail_id,
        guardrailVersion=guardrail_version,
        source="OUTPUT",
        content=[
            {"text": {"text": context_text, "qualifiers": ["grounding_source"]}},
            {"text": {"text": question_text, "qualifiers": ["query"]}},
            {"text": {"text": answer_text, "qualifiers": ["guard_content"]}},
        ],
    )
    intervened = response.get("action") == "GUARDRAIL_INTERVENED"
    message = None
    if intervened:
        outputs = response.get("outputs", [])
        message = outputs[0]["text"] if outputs else "Answer blocked by guardrail policy."
    return intervened, message


def verified_retrieve_and_generate(agent_client, runtime_client, question_text, knowledge_base_id,
                                    model_id, metadata_filter=None, number_of_results=5,
                                    guardrail_id=None, guardrail_version=None):
    """Retrieves top-k chunks via retrieve(), then generates a grounded answer via converse().

    Returns a dict: {answer, citations, distinct_reports_cited, grounded,
    guardrail_intervened, guardrail_stage, guardrail_message}.
    `grounded=False` means retrieve() returned zero results -- the question
    is never sent to the generation model in that case, so there is no
    fluent-but-ungrounded answer to accidentally trust.

    `guardrail_id`/`guardrail_version` are optional; pass both to run the
    Phase 6 two-call pattern (see module docstring). `guardrail_stage` is
    `"input"` (blocked before retrieve() ever ran), `"output"` (grounding/
    content check intervened after generation -- answer/citations are still
    returned, since Phase 6 found this check doesn't reliably catch a
    wrong-document answer and a false "all clear" is worse than an honest
    intervention flag), or `None` (guardrail not configured, or configured
    and passed clean).
    """
    guardrail_intervened, guardrail_stage, guardrail_message = False, None, None

    if guardrail_id:
        blocked, message = _apply_input_guardrail(
            runtime_client, guardrail_id, guardrail_version, question_text)
        if blocked:
            return {
                "answer": "", "citations": [], "distinct_reports_cited": [], "grounded": False,
                "guardrail_intervened": True, "guardrail_stage": "input", "guardrail_message": message,
            }

    vector_search_config = {"numberOfResults": number_of_results}
    if metadata_filter:
        vector_search_config["filter"] = metadata_filter

    retrieve_response = agent_client.retrieve(
        knowledgeBaseId=knowledge_base_id,
        retrievalQuery={"text": question_text},
        retrievalConfiguration={"vectorSearchConfiguration": vector_search_config},
    )
    results = retrieve_response.get("retrievalResults", [])

    citations = []
    context_blocks = []
    for res in results:
        uri = res.get("location", {}).get("s3Location", {}).get("uri", "")
        text = res.get("content", {}).get("text", "")
        citations.append({"source": uri, "snippet": text[:200]})
        context_blocks.append(f"[Source: {uri}]\n{text}")

    distinct_reports = []
    for c in citations:
        report_id = c["source"].rsplit("/", 1)[-1].replace(".txt", "")
        if report_id not in distinct_reports:
            distinct_reports.append(report_id)

    if not results:
        return {
            "answer": "", "citations": [], "distinct_reports_cited": [], "grounded": False,
            "guardrail_intervened": False, "guardrail_stage": None, "guardrail_message": None,
        }

    context = "\n\n".join(context_blocks)
    prompt = (
        "Answer the question using ONLY the sources below. Do not use outside "
        "knowledge, even if you recognize the topic. If the sources don't "
        "contain the answer, say so explicitly rather than guessing.\n\n"
        f"{context}\n\nQuestion: {question_text}"
    )
    converse_response = runtime_client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
    )
    answer_text = converse_response["output"]["message"]["content"][0]["text"]

    if guardrail_id:
        blocked, message = _apply_output_guardrail(
            runtime_client, guardrail_id, guardrail_version, context, question_text, answer_text)
        guardrail_intervened, guardrail_stage, guardrail_message = blocked, ("output" if blocked else None), message

    return {
        "answer": answer_text,
        "citations": citations,
        "distinct_reports_cited": distinct_reports,
        "grounded": True,
        "guardrail_intervened": guardrail_intervened,
        "guardrail_stage": guardrail_stage,
        "guardrail_message": guardrail_message,
    }


def retrieve_all_chunks(client, knowledge_base_id, report_id, query_text="summary findings cause",
                         max_results=100):
    """Pulls every indexed chunk for one report via a report_id metadata filter.

    Used for exhaustive per-document extraction, where the goal is complete
    coverage of a single document rather than top-k semantic relevance to a
    query. Returns [] if the filter matches nothing -- callers must treat
    that as a hard failure (an ingestion gap for that report_id), not skip
    it silently.
    """
    response = client.retrieve(
        knowledgeBaseId=knowledge_base_id,
        retrievalQuery={"text": query_text},
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": max_results,
                "filter": {"equals": {"key": "report_id", "value": report_id}},
            }
        },
    )
    return [r["content"]["text"] for r in response.get("retrievalResults", [])]


def estimate_cost_usd(input_tokens, output_tokens, input_rate_per_million, output_rate_per_million):
    return (input_tokens / 1_000_000) * input_rate_per_million + \
           (output_tokens / 1_000_000) * output_rate_per_million
