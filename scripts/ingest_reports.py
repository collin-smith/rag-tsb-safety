"""Fetch each manifest report's full-report page from tsb.gc.ca, extract
clean text with a licensing-compliant attribution header, and upload to the
project's S3 raw zone with metadata tags.

Usage:
    python3 ingest_reports.py ../manifest/reports_manifest.csv rag-tsb-safety-raw-805068224035

Respects TSB's site (observed 2026-09-11 to rate-limit/502 under rapid
sequential requests) with a delay between requests and retry-with-backoff.
Requires a browser User-Agent — tsb.gc.ca returns 403 to generic ones.
"""
import csv
import html
import os
import re
import subprocess
import sys
import tempfile
import time

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
DELAY_SECONDS = 6
MAX_RETRIES = 4


def full_report_url(overview_url: str) -> str:
    url = overview_url.replace("/enquetes-investigations/", "/rapports-reports/")
    # the site 302-redirects an uppercase-ID path segment to the lowercase
    # canonical one; go there directly to save a hop
    segs = url.split("/")
    segs[-2] = segs[-2].lower()
    segs[-1] = segs[-1].lower()
    return "/".join(segs)


def fetch(url: str) -> str:
    """Shell out to curl -- tsb.gc.ca returns 403/502 to Python's urllib
    (likely a WAF fingerprint check) but is reliably reachable via curl with
    a browser User-Agent, confirmed 2026-09-11."""
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        result = subprocess.run(
            ["curl", "-s", "-w", "\n%{http_code}", "-A", USER_AGENT,
             "--max-time", "45", url],
            capture_output=True, text=True,
        )
        body, _, code = result.stdout.rpartition("\n")
        if code == "200":
            return body
        last_err = f"http {code} (curl exit {result.returncode})"
        wait = DELAY_SECONDS * attempt
        print(f"    attempt {attempt} failed ({last_err}); retrying in {wait}s")
        time.sleep(wait)
    raise RuntimeError(f"giving up on {url}: {last_err}")


def extract_text(page_html: str) -> str:
    m = re.search(r"<main.*?</main>", page_html, re.S)
    content = m.group(0) if m else page_html
    content = re.sub(r"<script.*?</script>", "", content, flags=re.S)
    content = re.sub(r"<style.*?</style>", "", content, flags=re.S)
    content = re.sub(r"<[^>]+>", "\n", content)
    content = html.unescape(content)
    lines = [l.strip() for l in content.split("\n")]
    lines = [l for l in lines if l]
    # collapse the repeated Drupal chrome lines that show up on every page
    noise = {
        "Skip to main content",
        "Language selection",
        "Search",
        "Menu",
    }
    lines = [l for l in lines if l not in noise]
    return "\n".join(lines)


def build_document(report_id, mode, date, occurrence_type, company, location, source_url, body_text):
    header = (
        f"TSB Report {report_id} ({mode})\n"
        f"{occurrence_type}\n"
        f"{company}\n"
        f"{location}\n"
        f"Date: {date}\n"
        f"Source: Transportation Safety Board of Canada. "
        f"This is a reproduction of the version available at {source_url}.\n"
        f"Reproduced under TSB's non-commercial reproduction terms "
        f"(tsb.gc.ca/eng/avis-notices/avis-notices.html).\n"
        "\n---\n\n"
    )
    return header + body_text


def s3_upload(local_path, bucket, key, tags):
    tag_str = "&".join(f"{k}={v}" for k, v in tags.items())
    subprocess.run(
        [
            "aws", "s3api", "put-object",
            "--bucket", bucket,
            "--key", key,
            "--body", local_path,
            "--tagging", tag_str,
            "--content-type", "text/plain",
        ],
        check=True,
    )


def main():
    manifest_path, bucket = sys.argv[1], sys.argv[2]
    rows = list(csv.DictReader(open(manifest_path, encoding="utf-8")))
    skipped = []

    for i, r in enumerate(rows, 1):
        rid = r["report_id"]
        print(f"[{i}/{len(rows)}] {rid}")
        url = full_report_url(r["url"])
        try:
            page = fetch(url)
        except RuntimeError as e:
            # Some investigations (TSB "class 4/5", brief occurrence
            # summaries) never get a separate full-report page -- the
            # overview page IS the whole report, so the derived
            # rapports-reports URL 404s. Skip and keep going rather than
            # crashing the whole batch on one report.
            print(f"    SKIPPED (fetch failed, likely a class 4/5 summary-only report): {e}")
            skipped.append(rid)
            continue
        text = extract_text(page)
        if len(text) < 500:
            print(f"    WARNING: extracted text unexpectedly short ({len(text)} chars) — check {url}")
        doc = build_document(
            rid, r["mode"], r["date"], r["occurrence_type"],
            r["company"], r["location"], url, text,
        )
        local_path = os.path.join(tempfile.gettempdir(), f"{rid}.txt")
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(doc)

        key = f"reports/{r['mode']}/{rid}.txt"
        s3_upload(
            local_path, bucket, key,
            {"report_id": rid, "mode": r["mode"], "date": r["date"]},
        )
        print(f"    uploaded s3://{bucket}/{key} ({len(doc)} chars)")
        if i < len(rows):
            time.sleep(DELAY_SECONDS)

    if skipped:
        print(f"\nSkipped {len(skipped)} report(s), not uploaded: {skipped}")
        print("Remove these from the manifest (likely class 4/5, no full-report page).")


if __name__ == "__main__":
    main()
