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
"""
import json


def verified_retrieve_and_generate(agent_client, runtime_client, question_text, knowledge_base_id,
                                    model_id, metadata_filter=None, number_of_results=5):
    """Retrieves top-k chunks via retrieve(), then generates a grounded answer via converse().

    Returns a dict: {answer, citations, distinct_reports_cited, grounded}.
    `grounded=False` means retrieve() returned zero results -- the question
    is never sent to the generation model in that case, so there is no
    fluent-but-ungrounded answer to accidentally trust.
    """
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
        return {"answer": "", "citations": [], "distinct_reports_cited": [], "grounded": False}

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

    return {
        "answer": answer_text,
        "citations": citations,
        "distinct_reports_cited": distinct_reports,
        "grounded": True,
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
