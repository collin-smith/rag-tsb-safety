"""Parse TSB rail/pipeline report index pages (saved HTML) into a CSV of
report_id, mode, status, date, occurrence_type, company, location_detail, url.

Usage:
    curl -A "Mozilla/5.0 ..." https://www.tsb.gc.ca/eng/rapports-reports/rail/index.html -o rail.html
    curl -A "Mozilla/5.0 ..." https://www.tsb.gc.ca/eng/rapports-reports/pipeline/index.html -o pipeline.html
    python3 parse_tsb_index.py rail.html pipeline.html out.csv

Note: tsb.gc.ca returns 403 to generic/non-browser user agents (WebFetch-style
tools) — a browser User-Agent header is required.
"""
import re, sys, csv, html
from collections import Counter


def parse(path, mode):
    with open(path, encoding="utf-8") as f:
        content = f.read()

    row_re = re.compile(r'<tr class="(?:odd|even)">(.*?)</tr>', re.S)
    rows = row_re.findall(content)
    out = []
    for row in rows:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(tds) < 5:
            continue
        status = re.sub("<[^>]+>", "", tds[0]).strip()
        link_m = re.search(r'href="([^"]+)"[^>]*>([^<]+)<', tds[1])
        if not link_m:
            continue
        href, rid = link_m.group(1), link_m.group(2).strip()
        date_m = re.search(r'datetime="([^"]+)"', tds[2])
        date = date_m.group(1)[:10] if date_m else ""
        occ_html = tds[3]
        strong_m = re.search(r"<strong>(.*?)</strong>", occ_html, re.S)
        occ_type = (
            html.unescape(re.sub("<[^>]+>", "", strong_m.group(1))).strip()
            if strong_m
            else ""
        )
        spans = re.findall(r"<span[^>]*>(.*?)</span>", occ_html, re.S)
        fields = [
            html.unescape(re.sub("<[^>]+>", "", s)).replace("\xa0", " ").strip()
            for s in spans
        ]
        fields = [f for f in fields if f and f != occ_type]
        company = fields[0] if len(fields) > 0 else ""
        rest = fields[1:] if len(fields) > 1 else []
        out.append(
            {
                "mode": mode,
                "report_id": rid,
                "status": status,
                "date": date,
                "occurrence_type": occ_type,
                "company": company,
                "location_detail": " | ".join(rest),
                "url": "https://www.tsb.gc.ca" + href,
            }
        )
    return out


if __name__ == "__main__":
    rail = parse(sys.argv[1], "rail")
    pipeline = parse(sys.argv[2], "pipeline") if len(sys.argv) > 2 else []

    all_rows = rail + pipeline
    with open(sys.argv[3], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "mode",
                "report_id",
                "status",
                "date",
                "occurrence_type",
                "company",
                "location_detail",
                "url",
            ],
        )
        w.writeheader()
        w.writerows(all_rows)

    print(f"rail rows: {len(rail)}, pipeline rows: {len(pipeline)}, total: {len(all_rows)}")
    completed = [r for r in all_rows if r["status"] == "Completed"]
    print(f"completed: {len(completed)}")
    print("Top occurrence types:")
    for t, c in Counter(r["occurrence_type"] for r in completed).most_common(20):
        print(f"  {c:3d}  {t}")
