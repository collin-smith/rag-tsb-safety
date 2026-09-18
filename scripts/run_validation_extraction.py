"""Run the exact Phase 3 extraction pass (extract_one, unmodified) against
the 313 validation-sample reports that were actually fetched and indexed
(320 sampled, 7 skipped at fetch time -- no separate full-report page).
Writes to a separate output file so the original 57-report
structured_findings.json is untouched.
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clock_fix  # noqa: E402
import boto3  # noqa: E402
from extract_structured_findings import extract_one, NOVA_LITE_INPUT_RATE, NOVA_LITE_OUTPUT_RATE  # noqa: E402
from rag_utils import estimate_cost_usd  # noqa: E402

REGION = "ca-central-1"
SAMPLE_MANIFEST = os.path.join(os.environ.get("TMPDIR", "/tmp"), "validation_sample_320.csv")
UPLOAD_LOG = os.path.join(os.environ.get("TMPDIR", "/tmp"), "validation_ingest_log.jsonl")
OUT_JSON = os.path.join(os.environ.get("TMPDIR", "/tmp"), "validation_sample_findings.json")
OUT_CSV = os.path.join(os.environ.get("TMPDIR", "/tmp"), "validation_sample_findings.csv")
PROGRESS_LOG = os.path.join(os.environ.get("TMPDIR", "/tmp"), "validation_extraction_log.jsonl")


def main():
    uploaded_ids = set()
    for line in open(UPLOAD_LOG):
        rec = json.loads(line)
        if rec["status"] == "uploaded":
            uploaded_ids.add(rec["report_id"])

    rows = list(csv.DictReader(open(SAMPLE_MANIFEST, encoding="utf-8")))
    mode_by_id = {r["report_id"]: r["mode"] for r in rows}
    report_ids = [r["report_id"] for r in rows if r["report_id"] in uploaded_ids]
    print(f"{len(report_ids)} reports to extract (of {len(rows)} sampled)")

    done_ids = set()
    if os.path.exists(PROGRESS_LOG):
        for line in open(PROGRESS_LOG):
            done_ids.add(json.loads(line)["report_id"])
    remaining = [r for r in report_ids if r not in done_ids]
    if done_ids:
        print(f"Resuming: {len(done_ids)} already done, {len(remaining)} remaining")

    bedrock_runtime = boto3.client("bedrock-runtime", region_name=REGION)
    agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)

    logf = open(PROGRESS_LOG, "a", encoding="utf-8")
    for i, report_id in enumerate(remaining, 1):
        print(f"[{i}/{len(remaining)}] {report_id} ...", end=" ", flush=True)
        result = extract_one(bedrock_runtime, agent_runtime, report_id)
        result["mode"] = mode_by_id[report_id]
        logf.write(json.dumps(result) + "\n")
        logf.flush()
        if not result.get("grounded"):
            print("FAILED (no chunks retrieved)")
        elif result.get("parse_error"):
            print(f"JSON PARSE ERROR: {result['parse_error']}")
        else:
            print(f"ok -- {result.get('root_cause_category')}")
    logf.close()

    # assemble final output from the full progress log (covers resumed runs too)
    results = [json.loads(l) for l in open(PROGRESS_LOG)]
    total_in = sum(r.get("input_tokens", 0) for r in results)
    total_out = sum(r.get("output_tokens", 0) for r in results)
    cost = estimate_cost_usd(total_in, total_out, NOVA_LITE_INPUT_RATE, NOVA_LITE_OUTPUT_RATE)

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    fieldnames = ["report_id", "mode", "chunks_used", "grounded", "root_cause_category",
                  "dangerous_goods_involved", "fatality_count", "key_recommendation",
                  "prior_recommendation_unimplemented", "parse_error"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    failed = [r for r in results if not r.get("grounded")]
    parse_failed = [r for r in results if r.get("grounded") and r.get("parse_error")]
    print(f"\n{'=' * 70}")
    print(f"Processed {len(results)} reports: {len(failed)} retrieval failures, {len(parse_failed)} JSON parse failures.")
    print(f"Tokens: {total_in} in / {total_out} out. Measured cost @ Nova Lite rates: ${cost:.4f}")
    print(f"Wrote {OUT_JSON} and {OUT_CSV}")


if __name__ == "__main__":
    main()
