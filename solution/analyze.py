#!/usr/bin/env python3
import csv
import json
import os
import re
import subprocess
import sys
import tempfile

APP = sys.argv[1]
SCORER = os.path.join(APP, "repo", "score.py")
TESTSET = os.path.join(APP, "data", "testset.jsonl")
# Testset v1 is not shipped in the workspace; it survives only in the seed
# repo's git history. Recover it at commit 4 (HEAD~6, the harness revision that
# scored ckpt_a).
_v1_src = subprocess.check_output(
    ["git", "-C", os.path.join(APP, "repo"), "show", "HEAD~6:testset_v1.jsonl"],
    text=True,
)
_v1_tf = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
_v1_tf.write(_v1_src)
_v1_tf.close()
TESTSET_V1 = _v1_tf.name
PREDS_A = os.path.join(APP, "predictions", "preds_ckpt_a.jsonl")
PREDS_B = os.path.join(APP, "predictions", "preds_ckpt_b.jsonl")
RETRY = os.path.join(APP, "predictions", "preds_ckpt_b_retry.jsonl")


def read_jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def run_scorer(rows, testset=TESTSET):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as tf:
        for r in rows:
            tf.write(json.dumps(r) + "\n")
        path = tf.name
    try:
        out = subprocess.check_output(
            [sys.executable, SCORER, path, testset], text=True
        )
    finally:
        os.unlink(path)
    return json.loads(out.strip())


rows_a = read_jsonl(PREDS_A)
rows_b = read_jsonl(PREDS_B)
retry_rows = read_jsonl(RETRY)
testset_ids = [r["id"] for r in read_jsonl(TESTSET)]

dash = {}
with open(os.path.join(APP, "dashboard.csv")) as f:
    for row in csv.DictReader(f):
        dash[row["checkpoint"]] = float(row["accuracy_pct"])

# ---- Discovered confounds ----

# id-level intersection (1975 comparable rows)
# This ensures that the two runs are comparable at the row (ID) level. This is necessary
# because the scoring harness has a contract stating that it will score all rows in the predictions file.
# We know from the previous information gained during the patching of score.py that duplicates exist in ckpt_a
# and from docs/testset_changelog.md that unique rows were added to testset v2. Therefore, to make the comparison fair,
# we need to remove the duplicates and any rows not present in both runs.
ids_a = {r["id"] for r in rows_a}
ids_b = {r["id"] for r in rows_b}
C_id = ids_a & ids_b

# in-place re-annotation (1950 comparable rows)
# docs/testset_changelog.md states that the testset was re-annotated in place between the two runs.
# This means that some rows have different questions and answers between the two runs.
# To make the comparison fair, we need to remove any rows that were re-annotated.
v1_by_id = {r["id"]: r for r in read_jsonl(TESTSET_V1)}
v2_by_id = {r["id"]: r for r in read_jsonl(TESTSET)}
reannotated_ids = {
    i
    for i in C_id
    if v1_by_id[i]["answer"] != v2_by_id[i]["answer"]
    or v1_by_id[i]["question"] != v2_by_id[i]["question"]
}
C = C_id - reannotated_ids

# retry backfill (1950 comparable rows)
# The files in config/ tell us that the max_tokens was dropped from 1024 to 256 for the ckpt_b run.
# But we also have results from a rerun where the max_tokens was restored to 1024.
# docs/ckpt_b_retry_backfill.md documents that the retry backfill was intended to cover only the truncated rows (24 rows),
# but we discover that there are 6 additional rows that were backfilled but not truncated.
# Based on the instructions in docs/ckpt_b_retry_backfill.md, we only want to substitute the verified truncated rows, and ignore the spurious backfill rows.
marker = re.compile(r"answer\s*(?:is|:)", re.IGNORECASE)
truncated_ids = {
    r["id"] for r in rows_b if not marker.search(r["output"]) and len(r["output"]) > 900
}
retry_ids = {r["id"] for r in retry_rows}
unaffected_ids = retry_ids - truncated_ids
print(
    f"[verify] retry backfill: {len(retry_rows)} rows, {len(truncated_ids)} verified truncated rows, "
    f"{len(unaffected_ids)} spurious backfill rows"
)

# ---- Corrected datasets a_corr and b_corr ----
seen = set()
a_corr = []
for r in rows_a:
    if r["id"] in seen or r["id"] not in C:
        continue
    seen.add(r["id"])
    a_corr.append(r)

retry_by_id = {r["id"]: r for r in retry_rows}
b_before_retry = [r for r in rows_b if r["id"] in C]
# Substitute ONLY verified-truncated rows; ignore the spurious backfill rows
b_corr = [
    retry_by_id[r["id"]] if r["id"] in truncated_ids else r for r in b_before_retry
]

# ---- Score everything with the patched harness (via its CLI) ----
res_a_corr = run_scorer(a_corr)
res_b_corr = run_scorer(b_corr)
findings = {
    "corrected_score_a": res_a_corr["accuracy"],
    "corrected_score_b": res_b_corr["accuracy"],
}
with open(os.path.join(APP, "findings.json"), "w") as f:
    json.dump(findings, f, indent=2)
print(json.dumps(findings, indent=2))
