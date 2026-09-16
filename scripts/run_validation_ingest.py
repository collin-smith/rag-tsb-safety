"""Fetch + upload the 320-report validation sample to the existing S3
raw-zone bucket, using boto3 directly (not the `aws` CLI) since this
sandbox's broken system clock breaks CLI subprocess signing but can be
monkeypatched for an in-process boto3 client via clock_fix.

Reuses ingest_reports.py's fetch/extract_text/build_document logic
unmodified. Writes one text object + one metadata sidecar per report, same
convention as the original 57-report ingestion.
"""
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clock_fix  # noqa: E402  (must import before boto3 client creation)
import boto3  # noqa: E402
from ingest_reports import fetch, full_report_url, extract_text, build_document  # noqa: E402

BUCKET = "rag-tsb-safety-raw-ca-805068224035"
REGION = "ca-central-1"
SAMPLE_MANIFEST = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.environ.get("TMPDIR", "/tmp"), "validation_sample_320.csv"
)
LOG_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "validation_ingest_log.jsonl")
DELAY_SECONDS = 6

s3 = boto3.client("s3", region_name=REGION)


def metadata_doc(rid, mode, date):
    attrs = {
        "report_id": {"value": {"type": "STRING", "stringValue": rid}, "includeForEmbedding": False},
        "mode": {"value": {"type": "STRING", "stringValue": mode}, "includeForEmbedding": False},
    }
    # A small number of older TSB entries (safety issue investigations /
    # "SII" studies, report_id prefix "SA" rather than a mode-letter+year
    # occurrence ID) carry no date in the index at all -- a genuine TSB
    # data-quality gap, not a fetch/parse error. Omit date_numeric rather
    # than crash or fabricate a value; the extraction pass filters by
    # report_id only, so this doesn't affect retrieval.
    if date and date.strip():
        attrs["date_numeric"] = {"value": {"type": "NUMBER", "numberValue": int(date.replace("-", ""))}, "includeForEmbedding": False}
    return {
        "metadataAttributes": attrs
    }


def main():
    rows = list(csv.DictReader(open(SAMPLE_MANIFEST, encoding="utf-8")))
    print(f"Loaded {len(rows)} rows from {SAMPLE_MANIFEST}")

    done_ids = set()
    if os.path.exists(LOG_PATH):
        for line in open(LOG_PATH):
            try:
                rec = json.loads(line)
                if rec.get("status") in ("uploaded", "skipped"):
                    done_ids.add(rec["report_id"])
            except json.JSONDecodeError:
                pass
    if done_ids:
        print(f"Resuming: {len(done_ids)} already processed, skipping those.")

    logf = open(LOG_PATH, "a", encoding="utf-8")
    remaining = [r for r in rows if r["report_id"] not in done_ids]
    for i, r in enumerate(remaining, 1):
        rid = r["report_id"]
        print(f"[{i}/{len(remaining)}] {rid} ...", end=" ", flush=True)
        url = full_report_url(r["url"])
        try:
            page = fetch(url)
        except RuntimeError as e:
            print("SKIPPED (fetch failed)")
            logf.write(json.dumps({"report_id": rid, "status": "skipped", "reason": str(e)}) + "\n")
            logf.flush()
            continue

        text = extract_text(page)
        if len(text) < 500:
            print(f"WARNING short text ({len(text)} chars), uploading anyway")

        doc = build_document(rid, r["mode"], r["date"], r["occurrence_type"], r["company"], r["location"], url, text)
        key = f"reports/{r['mode']}/{rid}.txt"
        meta_key = f"{key}.metadata.json"

        s3.put_object(
            Bucket=BUCKET, Key=key, Body=doc.encode("utf-8"),
            ContentType="text/plain",
            Tagging=f"report_id={rid}&mode={r['mode']}&date={r['date']}",
        )
        s3.put_object(
            Bucket=BUCKET, Key=meta_key,
            Body=json.dumps(metadata_doc(rid, r["mode"], r["date"])).encode("utf-8"),
            ContentType="application/json",
        )
        print(f"uploaded ({len(doc)} chars)")
        logf.write(json.dumps({"report_id": rid, "status": "uploaded", "chars": len(doc)}) + "\n")
        logf.flush()

        if i < len(remaining):
            time.sleep(DELAY_SECONDS)

    logf.close()
    print("\nDone with fetch+upload phase.")


if __name__ == "__main__":
    main()
