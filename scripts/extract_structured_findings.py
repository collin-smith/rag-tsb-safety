"""Exhaustive structured extraction over every report in the corpus.

Fixes the failure mode named in demo/insight_exploration.md's takeaway:
plain top-k vector search is good at "find a fact and cite it" but cannot
"count every instance of X" or "guarantee balanced coverage across
categories" -- those need a different mechanism, not a bigger
numberOfResults. This script is that different mechanism: an explicit loop
over the full manifest (not a semantic query hoping to touch every
document), pulling every indexed chunk for each report via a report_id
metadata filter (rag_utils.retrieve_all_chunks), then asking Nova Lite to
extract a fixed set of structured fields per report.

This is the "agent" half of the project, not the "RAG" half: a tool-using
loop that iterates a known document list and calls an LLM once per item,
producing a structured table that CAN be counted and aggregated honestly
-- unlike a single retrieve_and_generate answer.

Grounding guarantee: a report_id filter can only return chunks that belong
to that report, so every extraction is grounded by construction. The gate
enforced here is simpler than rag_utils.verified_retrieve_and_generate's
citation check -- it's "zero chunks returned = hard failure for this
report", logged and skipped, never silently defaulted.

Usage:
    .venv/bin/python3 scripts/extract_structured_findings.py [--limit N]
"""
import argparse
import csv
import json
import os
import re
import sys

import boto3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rag_utils import retrieve_all_chunks, estimate_cost_usd  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(REPO_ROOT, "manifest", "reports_manifest.csv")
OUT_DIR = os.environ.get("EXTRACTION_OUT_DIR", os.path.join(REPO_ROOT, "demo"))
OUT_JSON = os.path.join(OUT_DIR, "structured_findings.json")
OUT_CSV = os.path.join(OUT_DIR, "structured_findings.csv")

REGION = "us-east-1"
KNOWLEDGE_BASE_ID = "LVBYRHRW4C"
GENERATION_MODEL_ID = "amazon.nova-lite-v1:0"
NOVA_LITE_INPUT_RATE = 0.06   # USD per million tokens
NOVA_LITE_OUTPUT_RATE = 0.24  # USD per million tokens

EXTRACTION_PROMPT = """You are extracting structured facts from excerpts of ONE Transportation \
Safety Board of Canada investigation report (report {report_id}). The excerpts below may not be \
in original document order -- read all of them before answering.

Return ONLY a single JSON object (no markdown fences, no commentary) with exactly these keys:
- "root_cause_category": a short phrase (3-8 words) naming the primary cause identified
- "dangerous_goods_involved": true or false -- were dangerous goods / hazardous materials part of \
this occurrence?
- "fatality_count": an integer (0 if none stated), or null if the excerpts don't say
- "key_recommendation": the single most significant safety recommendation made, as one sentence, \
or null if no recommendation appears in the excerpts
- "prior_recommendation_unimplemented": true if the report states an earlier safety recommendation \
(from TSB or elsewhere) had not been fully implemented and contributed to this occurrence; false if \
no such statement appears; null if unclear

If information for a field genuinely isn't in the excerpts, use null or false as specified above \
-- never guess or fill in from general knowledge.

EXCERPTS:
{excerpts}
"""


def extract_one(bedrock_runtime, agent_runtime, report_id):
    chunks = retrieve_all_chunks(agent_runtime, KNOWLEDGE_BASE_ID, report_id)
    if not chunks:
        return {"report_id": report_id, "error": "NO_CHUNKS_RETRIEVED", "grounded": False}

    excerpts = "\n\n---\n\n".join(chunks)
    prompt = EXTRACTION_PROMPT.format(report_id=report_id, excerpts=excerpts)

    response = bedrock_runtime.converse(
        modelId=GENERATION_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 400, "temperature": 0},
    )
    raw_text = response["output"]["message"]["content"][0]["text"]
    usage = response.get("usage", {})

    cleaned = re.sub(r"^```(json)?|```$", "", raw_text.strip(), flags=re.MULTILINE).strip()
    try:
        fields = json.loads(cleaned)
        parse_error = None
    except json.JSONDecodeError as e:
        fields = {}
        parse_error = str(e)

    return {
        "report_id": report_id,
        "chunks_used": len(chunks),
        "grounded": True,
        "parse_error": parse_error,
        "raw_response": raw_text if parse_error else None,
        "input_tokens": usage.get("inputTokens", 0),
        "output_tokens": usage.get("outputTokens", 0),
        **fields,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                         help="process only the first N reports (for a cheap test run)")
    args = parser.parse_args()

    with open(MANIFEST_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    report_ids = [r["report_id"] for r in rows]
    if args.limit:
        report_ids = report_ids[:args.limit]

    bedrock_runtime = boto3.client("bedrock-runtime", region_name=REGION)
    agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)

    results = []
    total_in, total_out = 0, 0
    for i, report_id in enumerate(report_ids, 1):
        print(f"[{i}/{len(report_ids)}] {report_id} ...", end=" ", flush=True)
        result = extract_one(bedrock_runtime, agent_runtime, report_id)
        results.append(result)
        total_in += result.get("input_tokens", 0)
        total_out += result.get("output_tokens", 0)
        if not result.get("grounded"):
            print("FAILED (no chunks retrieved)")
        elif result.get("parse_error"):
            print(f"JSON PARSE ERROR: {result['parse_error']}")
        else:
            print(f"ok -- {result.get('root_cause_category')}")

    failed = [r for r in results if not r.get("grounded")]
    parse_failed = [r for r in results if r.get("grounded") and r.get("parse_error")]
    cost = estimate_cost_usd(total_in, total_out, NOVA_LITE_INPUT_RATE, NOVA_LITE_OUTPUT_RATE)

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    fieldnames = ["report_id", "chunks_used", "grounded", "root_cause_category",
                  "dangerous_goods_involved", "fatality_count", "key_recommendation",
                  "prior_recommendation_unimplemented", "parse_error"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    print(f"\n{'=' * 70}")
    print(f"Processed {len(results)} reports: {len(failed)} retrieval failures, "
          f"{len(parse_failed)} JSON parse failures.")
    print(f"Tokens: {total_in} in / {total_out} out. "
          f"Measured cost @ Nova Lite rates: ${cost:.4f}")
    print(f"Wrote {OUT_JSON} and {OUT_CSV}")


if __name__ == "__main__":
    main()
