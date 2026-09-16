"""Retrieve-and-generate demo over the rag-tsb-safety Knowledge Base.

Run from anywhere; results are written to demo/demo_results.json relative
to the repo root regardless of the current working directory.

Asks a small set of real questions -- including one deliberately ambiguous
one that exposes a retrieval weak spot -- and prints grounded, cited
answers. This is the core artifact for the project's article (beat: "the
demo") and for interview show-and-tell.

Generation model: Amazon Nova Lite, not an Anthropic Claude model. Bedrock
started requiring a one-time "model use case details" form submission for
Anthropic models partway through this project (a new, account-level gate
that appeared mid-build, unrelated to anything in this repo) -- filling
that out requires the account owner's own business/use-case details, so
rather than block on it the demo uses a different Bedrock-native model
that was already unblocked. Retrieval itself (the actual "RAG" part) is
unaffected either way -- it's independent of which model does generation.

Uses rag_utils.verified_retrieve_and_generate (explicit retrieve() then
converse(), not Bedrock's retrieve_and_generate convenience API) -- see
rag_utils.py's module docstring for why: that API was found to silently
diverge from this KB's own retrieve() results on ca-central-1.

Usage:
    .venv/bin/python3 scripts/demo.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clock_fix  # noqa: E402  (must import before boto3 client creation; sandbox clock drifts)
import boto3  # noqa: E402
from rag_utils import verified_retrieve_and_generate  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_PATH = os.path.join(REPO_ROOT, "demo", "demo_results.json")

REGION = "ca-central-1"
KNOWLEDGE_BASE_ID = "Z3Q6F4RTPY"
# Nova Lite has no on-demand invocation in ca-central-1 (INFERENCE_PROFILE
# only, confirmed 2026-09-15) -- this is the CA geographic inference
# profile ("Routes requests to Nova Lite in ca-central-1 and ca-west-1"),
# not the us-east-1 foundation-model ARN this used to point at.
GENERATION_MODEL_ID = "ca.amazon.nova-lite-v1:0"
NUMBER_OF_RESULTS = 5

QUESTIONS = [
    {
        "label": "Flagship report / citation quality",
        "text": "What corrective actions were recommended after the Lac-Megantic derailment?",
    },
    {
        "label": "Cross-report synthesis",
        "text": "What types of track or equipment defects caused derailments in this set of reports?",
    },
    {
        "label": "CPKC relevance",
        "text": "What caused the CPKC crossing collision near Cramahe, Ontario in 2025?",
    },
    {
        "label": "Trans Mountain / energy-sector relevance",
        "text": "What caused the crude oil release at the Trans Mountain pipeline's Darfield pump station?",
    },
    {
        "label": "DELIBERATE WEAK SPOT: temporal/ambiguous query",
        "text": "What was the most recent incident in this dataset, and what caused it?",
    },
]


def run_query(bedrock_runtime, agent_runtime, question_text, metadata_filter=None):
    result = verified_retrieve_and_generate(
        agent_runtime, bedrock_runtime, question_text, KNOWLEDGE_BASE_ID, GENERATION_MODEL_ID,
        metadata_filter=metadata_filter, number_of_results=NUMBER_OF_RESULTS,
    )
    return result["answer"], result["citations"]


def print_and_record(bedrock_runtime, agent_runtime, label, question_text, metadata_filter=None):
    print(f"\n{'=' * 80}\n[{label}]\nQ: {question_text}\n{'-' * 80}")
    answer, citations = run_query(bedrock_runtime, agent_runtime, question_text, metadata_filter)
    print(f"A: {answer}\n")
    print(f"Cited sources ({len(citations)} chunks):")
    seen_reports = []
    for c in citations:
        report_id = c["source"].rsplit("/", 1)[-1].replace(".txt", "")
        if report_id not in seen_reports:
            seen_reports.append(report_id)
        print(f"  - {c['source']}")
    print(f"Distinct reports cited: {seen_reports}")
    return {
        "label": label,
        "question": question_text,
        "filter": metadata_filter,
        "answer": answer,
        "citations": citations,
        "distinct_reports_cited": seen_reports,
    }


def main():
    bedrock_runtime = boto3.client("bedrock-runtime", region_name=REGION)
    agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)
    results = []

    for q in QUESTIONS:
        results.append(print_and_record(bedrock_runtime, agent_runtime, q["label"], q["text"]))

    # The weak-spot query, fixed: plain vector similarity has no concept of
    # recency, so it surfaced a 2019 report as "most recent" even though the
    # corpus runs to 2026 (see the un-filtered run above). The fix isn't a
    # better prompt or more retrieved chunks -- it's structured metadata.
    # Each chunk was re-ingested with a `date_numeric` (YYYYMMDD int)
    # attribute (build_metadata_sidecars.py), letting retrieval be
    # constrained with a real filter instead of relying on semantic
    # similarity to a word like "recent".
    results.append(print_and_record(
        bedrock_runtime, agent_runtime,
        "WEAK SPOT, FIXED: same query with a date_numeric metadata filter",
        "What was the most recent incident in this dataset, and what caused it?",
        metadata_filter={"greaterThan": {"key": "date_numeric", "value": 20260101}},
    ))

    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n{'=' * 80}\nSaved full results (including chunk snippets) to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
