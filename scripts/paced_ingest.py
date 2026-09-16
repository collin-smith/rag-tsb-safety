"""Ingest manifest documents into the Knowledge Base a few at a time, with
delays, instead of using start-ingestion-job (which fans out embedding calls
for the whole corpus at once and blows through this account's hard,
non-adjustable 60 requests/minute Titan Embed V2 quota -- confirmed via
`aws service-quotas list-service-quotas --service-code bedrock` and
CloudWatch InvocationThrottles during two failed start-ingestion-job runs,
2026-09-11/12).

Usage:
    python3 paced_ingest.py ../manifest/reports_manifest.csv KYB9WIZOZI OYZVX7XNXY rag-tsb-safety-raw-805068224035
"""
import csv
import json
import subprocess
import sys
import time

DELAY_BETWEEN_BATCHES = 75  # seconds
LARGE_DOC_BYTES = 150_000  # ingest solo, one at a time, above this size
POLL_INTERVAL = 5
POLL_TIMEOUT = 240


def run_aws(args):
    result = subprocess.run(["aws"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def ingest_batch(kb_id, ds_id, uris):
    docs = [
        {"content": {"dataSourceType": "S3", "s3": {"s3Location": {"uri": uri}}}}
        for uri in uris
    ]
    return run_aws([
        "bedrock-agent", "ingest-knowledge-base-documents",
        "--knowledge-base-id", kb_id,
        "--data-source-id", ds_id,
        "--documents", json.dumps(docs),
        "--region", "us-east-1",
    ])


def poll_statuses(kb_id, ds_id, uris):
    deadline = time.time() + POLL_TIMEOUT
    pending = set(uris)
    final = {}
    while pending and time.time() < deadline:
        idents = [{"dataSourceType": "S3", "s3": {"uri": u}} for u in pending]
        result = run_aws([
            "bedrock-agent", "get-knowledge-base-documents",
            "--knowledge-base-id", kb_id,
            "--data-source-id", ds_id,
            "--document-identifiers", json.dumps(idents),
            "--region", "us-east-1",
        ])
        for d in result.get("documentDetails", []):
            uri = d["identifier"]["s3"]["uri"]
            status = d["status"]
            if status in ("INDEXED", "FAILED", "IGNORED"):
                final[uri] = status
                pending.discard(uri)
        if pending:
            time.sleep(POLL_INTERVAL)
    for u in pending:
        final[u] = "TIMEOUT"
    return final


def object_sizes(bucket):
    result = run_aws([
        "s3api", "list-objects-v2", "--bucket", bucket, "--prefix", "reports/",
        "--query", "Contents[].{Key:Key,Size:Size}",
    ])
    return {o["Key"]: o["Size"] for o in result}


def build_batches(uris_with_sizes):
    """Ascending by size; anything over LARGE_DOC_BYTES goes solo."""
    ordered = sorted(uris_with_sizes, key=lambda t: t[1])
    batches = []
    current = []
    for uri, size in ordered:
        if size > LARGE_DOC_BYTES:
            if current:
                batches.append(current)
                current = []
            batches.append([uri])
        else:
            current.append(uri)
            if len(current) == 3:
                batches.append(current)
                current = []
    if current:
        batches.append(current)
    return batches


def main():
    manifest_path, kb_id, ds_id, bucket = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    rows = list(csv.DictReader(open(manifest_path, encoding="utf-8")))

    def s3_key(r):
        return f"reports/{r['mode']}/{r['report_id']}.txt"

    sizes = object_sizes(bucket)
    uris_with_sizes = [
        (f"s3://{bucket}/{s3_key(r)}", sizes[s3_key(r)]) for r in rows
    ]
    batches = build_batches(uris_with_sizes)

    results = {}
    for i, batch in enumerate(batches, 1):
        print(f"[batch {i}/{len(batches)}] ingesting {batch}")
        ingest_batch(kb_id, ds_id, batch)
        statuses = poll_statuses(kb_id, ds_id, batch)
        for u, s in statuses.items():
            print(f"    {u}: {s}")
        results.update(statuses)
        if i < len(batches):
            print(f"    sleeping {DELAY_BETWEEN_BATCHES}s before next batch")
            time.sleep(DELAY_BETWEEN_BATCHES)

    print("\n=== summary ===")
    for status in ("INDEXED", "FAILED", "IGNORED", "TIMEOUT"):
        n = sum(1 for s in results.values() if s == status)
        print(f"{status}: {n}")
    if any(s != "INDEXED" for s in results.values()):
        print("\nnot indexed:")
        for u, s in results.items():
            if s != "INDEXED":
                print(f"  {s}: {u}")


if __name__ == "__main__":
    main()
