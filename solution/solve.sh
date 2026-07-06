#!/usr/bin/env bash
set -euo pipefail

APP="${TASK_APP:-/app}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Deliverable 1: patch score.py ----

# Run a Python script to check for duplicate IDs and extraction coverage in the predictions and testset files.
# We discover the following:
# 1. preds_ckpt_a.jsonl has 40 duplicate IDs
# 2. preds_ckpt_a.jsonl has 0 extraction hits (all outputs end with "the answer is X" instead of "answer: X")
# 3. preds_ckpt_b.jsonl misses extractions due to markdown formatting (e.g., "Final answer: **75**" instead of "answer: 75")
python3 - <<'PY'
import json, glob, re
for path in ['/app/data/testset.jsonl','/app/predictions/preds_ckpt_a.jsonl','/app/predictions/preds_ckpt_b.jsonl','/app/predictions/preds_ckpt_b_retry.jsonl']:
    ids=[]
    rows=[]
    with open(path) as f:
        for line in f:
            if line.strip():
                row=json.loads(line); rows.append(row); ids.append(row['id'])
    print(path, 'lines', len(ids), 'unique', len(set(ids)), 'dups', len(ids)-len(set(ids)))
    if len(ids)!=len(set(ids)):
        from collections import Counter
        print(' dup examples', [x for x,c in Counter(ids).items() if c>1][:10])
# current extraction coverage and sample misses
pat=re.compile(r'answer:\s*(-?\d+(?:\.\d+)?)', re.I)
for path in ['/app/predictions/preds_ckpt_a.jsonl','/app/predictions/preds_ckpt_b.jsonl','/app/predictions/preds_ckpt_b_retry.jsonl']:
    miss=[]; hit=0
    with open(path) as f:
        for line in f:
            row=json.loads(line)
            if pat.search(row['output']): hit+=1
            elif len(miss)<5: miss.append((row['id'], row['output'][:160]))
    print('\nextract current', path, 'hit', hit, 'miss', sum(1 for _ in open(path))-hit)
    print('miss samples:', miss)
PY

# Sample output from the above Python script:
# /app/data/testset.jsonl lines 2000 unique 2000 dups 0
# /app/predictions/preds_ckpt_a.jsonl lines 2040 unique 2000 dups 40
#  dup examples ['q0030', 'q0954', 'q0748', 'q0169', 'q0313', 'q1271', 'q0630', 'q0601', 'q0462', 'q1260']
# /app/predictions/preds_ckpt_b.jsonl lines 2000 unique 2000 dups 0
# /app/predictions/preds_ckpt_b_retry.jsonl lines 30 unique 30 dups 0
# extract current /app/predictions/preds_ckpt_a.jsonl hit 0 miss 2040
# miss samples: [('q1804', '...the answer is 40.'), ('q1673', '...the answer is 91.'), ('q0157', '...I believe the answer is 37.'), ('q0318', '...I believe the answer is 75.'), ('q0833', '...The answer is 130.')]
# extract current /app/predictions/preds_ckpt_b.jsonl hit 1846 miss 154
# miss samples: [('q0042', 'Final answer: **75**'), ('q0054', 'Final answer: **2850**'), ('q0069', 'Final answer: **39**'), ('q0106', 'Final answer: **265**'), ('q0146', 'Final answer: **12**')]
# extract current /app/predictions/preds_ckpt_b_retry.jsonl hit 26 miss 4
# miss samples: [('q0505', 'Final answer: **127**'), ('q1924', 'Final answer: **92**'), ('q0759', 'Final answer: **61**'), ('q0442', 'Final answer: **78**')]

# Patch extract_answer() in score.py to handle every answer-bearing style present in the cached runs:
#   - "the answer is <value>"                     (ckpt_a era template)
#   - "Answer: <value>" / "Answer: <value>."      (ckpt_b era template)
#   - "Final answer: **<value>**"                 (ckpt_b markdown-bold)
# No other functions need to be changed.
cp "$SCRIPT_DIR/score.py" "$APP/repo/score.py"

# ---- Deliverable 2: /app/findings.json ----

# docs/testset_changelog.md describes an in-place re-annotation
# Look through the git history to find the commit number of the original testset (v1)
# in order to compare the questions and answers to v2.
find /app -maxdepth 3 -type f -printf '%p\\n' | sort && echo '--- git status/log ---' && cd /app/repo && git status --short && git log --oneline --all --decorate --stat -5

# The remaining rationales are located in the Python script below, which produces /app/findings.json.
python "$SCRIPT_DIR/analyze.py" "$APP"

echo "[oracle] done."
