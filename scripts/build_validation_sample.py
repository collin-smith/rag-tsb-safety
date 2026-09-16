#!/usr/bin/env python3
"""Build a stratified random validation sample from the full TSB indexes,
excluding the 57 reports already in the curated corpus.

Sampling frame is restricted to status == "Completed" (Active investigations
have no final report text to fetch), which changes the population from the
oft-quoted 2,422 to the honest 2,336. Sample size and mode allocation are
proportional to each mode's real share of that completed population.
"""
import csv
import random

SEED = 20260914
random.seed(SEED)

N_SAMPLE = 320

INDEX_FILES = [
    "/mnt/c/projects/it/ragproject/inputs/tsb_full_report_index_2026-09-11.csv",
    "/mnt/c/projects/it/ragproject/inputs/tsb_marine_aviation_full_index_2026-09-12.csv",
]
CURATED_MANIFEST = "/mnt/c/projects/it/ragproject/code/rag-tsb-safety/manifest/reports_manifest.csv"
import os
OUT_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "validation_sample_320.csv")

curated_ids = set()
with open(CURATED_MANIFEST) as f:
    for row in csv.DictReader(f):
        curated_ids.add(row["report_id"].strip().upper())

by_mode = {}
for fn in INDEX_FILES:
    with open(fn) as f:
        for row in csv.DictReader(f):
            if row["status"] != "Completed":
                continue
            rid = row["report_id"].strip().upper()
            if rid in curated_ids:
                continue
            by_mode.setdefault(row["mode"], []).append(row)

pop_counts = {m: len(v) for m, v in by_mode.items()}
total_pop = sum(pop_counts.values())
print("Eligible population (Completed, excluding curated 57):", pop_counts, "total:", total_pop)

# Proportional allocation with largest-remainder rounding so counts sum exactly to N_SAMPLE
raw = {m: N_SAMPLE * c / total_pop for m, c in pop_counts.items()}
alloc = {m: int(v) for m, v in raw.items()}
remainder = N_SAMPLE - sum(alloc.values())
order = sorted(raw, key=lambda m: raw[m] - alloc[m], reverse=True)
for m in order[:remainder]:
    alloc[m] += 1

print("Sample allocation:", alloc, "total:", sum(alloc.values()))

sample_rows = []
for mode, n in alloc.items():
    pool = by_mode[mode]
    chosen = random.sample(pool, n)
    for row in chosen:
        sample_rows.append(row)

random.shuffle(sample_rows)

fieldnames = ["report_id", "mode", "date", "occurrence_type", "company", "location", "url", "notes"]
with open(OUT_PATH, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for row in sample_rows:
        w.writerow({
            "report_id": row["report_id"],
            "mode": row["mode"],
            "date": row["date"],
            "occurrence_type": row["occurrence_type"],
            "company": row.get("company", ""),
            "location": row.get("location_detail", ""),
            "url": row["url"],
            "notes": "validation_sample_320",
        })

print(f"Wrote {len(sample_rows)} rows to {OUT_PATH}")
print("Seed:", SEED)
