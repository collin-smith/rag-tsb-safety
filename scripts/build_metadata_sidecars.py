"""Generate and upload Bedrock KB metadata sidecar files for each report.

Attaches a `date_numeric` (YYYYMMDD integer) metadata attribute per report
so retrieval can be filtered by date -- plain vector similarity has no
concept of recency, which is exactly the weak spot demo.py demonstrates and
fixes. Also attaches report_id and mode for good measure.

Bedrock's S3 data source convention: a sidecar file named
`<key>.metadata.json` next to `<key>` is picked up on the next sync and its
`metadataAttributes` get attached to every chunk from that document.

Usage:
    .venv/bin/python3 scripts/build_metadata_sidecars.py ../manifest/reports_manifest.csv rag-tsb-safety-raw-805068224035
    aws bedrock-agent start-ingestion-job --knowledge-base-id <kb> --data-source-id <ds>
"""
import csv
import json
import subprocess
import sys
import tempfile
import os


def main():
    manifest_path, bucket = sys.argv[1], sys.argv[2]
    rows = list(csv.DictReader(open(manifest_path, encoding="utf-8")))

    with tempfile.TemporaryDirectory() as tmpdir:
        for r in rows:
            date_numeric = int(r["date"].replace("-", ""))
            meta = {
                "metadataAttributes": {
                    "date_numeric": {
                        "value": {"type": "NUMBER", "numberValue": date_numeric},
                        "includeForEmbedding": False,
                    },
                    "report_id": {
                        "value": {"type": "STRING", "stringValue": r["report_id"]},
                        "includeForEmbedding": False,
                    },
                    "mode": {
                        "value": {"type": "STRING", "stringValue": r["mode"]},
                        "includeForEmbedding": False,
                    },
                }
            }
            local_path = os.path.join(tmpdir, f"{r['report_id']}.txt.metadata.json")
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(meta, f)

            key = f"reports/{r['mode']}/{r['report_id']}.txt.metadata.json"
            subprocess.run(
                ["aws", "s3", "cp", local_path, f"s3://{bucket}/{key}",
                 "--content-type", "application/json"],
                check=True, capture_output=True,
            )
            print(f"uploaded {key} (date_numeric={date_numeric})")

    print("\nRun start-ingestion-job to pick up the new metadata.")


if __name__ == "__main__":
    main()
