#!/usr/bin/env python3
import json
import os
import random
import re
import sys

SEED = 20260702

N_V1 = 2000
N_REMOVED = 25
N_NEW = 25
N_REANNOTATED = 25  # retained ids whose question+gold changed v1->v2
N_COMMON = N_V1 - N_REMOVED  # 1975 (id-level intersection)
N_FAIR = N_COMMON - N_REANNOTATED  # 1950 (comparable common set C)

N_A_CORRECT_FAIR = 1521  # ckpt_a correct among the 1950 comparable items
N_A_CORRECT_REANNOT = 20  # ckpt_a correct on re-annotated items (vs v1 wording)
N_A_CORRECT_REMOVED = 20
N_DUP_ROWS = 40  # all on correct comparable items

N_TRUNC = 24  # ckpt_b rows that hit the 256-token cap
N_TRUNC_RETRY_CORRECT = 15
N_TRUNC_RETRY_BOLD = 4  # retries emitted in the bold template
N_SPURIOUS_BACKFILL = 6  # #1: backfill rows for ids that were NOT capped
N_BOLD = 130  # ckpt_b bold-template rows (disjoint from trunc)
N_BOLD_CORRECT = 100
N_B_CORRECT_NEW = 12
N_B_CORRECT_REANNOT = 20  # ckpt_b correct on re-annotated items (vs v2 wording)
# ckpt_b correct within the comparable (fair) set, with retries substituted:
N_B_CORRECT_FAIR = 1550  # = 15 trunc + 100 bold + 1435 normal
N_B_CORRECT_NORMAL_FAIR = (
    N_B_CORRECT_FAIR - N_BOLD_CORRECT - N_TRUNC_RETRY_CORRECT
)  # 1435

OPS = ["+", "-", "*"]
CONTEXTS = [
    "A batch job processed {a} records; the operator then applied the transform '{op} {b}'.",
    "A sensor logged a base reading of {a} and a calibration step of '{op} {b}' was applied.",
    "Inventory started at {a} units and the ledger recorded the adjustment '{op} {b}'.",
    "A meter showed {a} at midnight; the correction '{op} {b}' was applied at rollover.",
]

A_TEMPLATES = [
    "Let me reason step by step. First I set up the computation carefully and simplify. The answer is {v}.",
    "Working through the arithmetic term by term gives a clear result. I believe the answer is {v}.",
    "After checking my work twice, the answer is {v}.",
]


def make_item(rng, idx):
    a = rng.randint(12, 97)
    b = rng.randint(3, 41)
    op = rng.choice(OPS)
    ans = {"+": a + b, "-": a - b, "*": a * b}[op]
    ctx = rng.choice(CONTEXTS).format(a=a, op=op, b=b)
    q = f"{ctx} What is the resulting value? Compute {a} {op} {b}."
    return {
        "id": f"q{idx:04d}",
        "question": q,
        "answer": str(ans),
        "_a": a,
        "_b": b,
        "_op": op,
    }


def wrong_value(rng, true_val):
    delta = rng.choice([-9, -7, -4, -3, -2, -1, 1, 2, 3, 4, 6, 8])
    return str(int(true_val) + delta)


def a_output(rng, val):
    return rng.choice(A_TEMPLATES).format(v=val)


def b_output(rng, val, bold):
    if bold:
        return f"Reasoning complete. Final answer: **{val}**"
    return rng.choice([f"Answer: {val}", f"Answer: {val}."])


_TRUNC_FILLER = (
    "Restating once more so the bookkeeping stays honest, the base quantity "
    "is unchanged and the adjustment is applied exactly once, so the whole "
    "computation is a single arithmetic step whose result I will spell out "
    "in full once every partial quantity has been carried forward. "
)


def truncated_output(rng, item):
    """A long reasoning trace cut off mid-word by the 256-token cap.

    Contains no final-answer marker and no digit sequence equal to the gold
    answer (only the operands appear, and truncated items are selected so
    that neither operand equals gold). ~1000+ chars ~= 256 tokens.
    """
    a, b, op = item["_a"], item["_b"], item["_op"]
    opw = {"+": "adding", "-": "subtracting", "*": "multiplying by"}[op]
    body = (
        f"Let me work through this carefully rather than rushing to a value. "
        f"We start from {a} and the record applies the adjustment '{op} {b}', "
        f"which amounts to {opw} {b} in a single step. To keep everything "
        "auditable I will restate the setup in words, carry each partial "
        "quantity forward explicitly, and only then combine the pieces into "
        "one final figure. "
    )
    text = body + _TRUNC_FILLER * 6
    cut = 1004 + rng.randint(0, 48)
    # Land the cut strictly inside a word so the output visibly stops
    # mid-token, the way a hard generation cap does.
    while cut < len(text) and not (text[cut - 1].isalpha() and text[cut].isalpha()):
        cut += 1
    return text[:cut]


def main(outdir):
    rng = random.Random(SEED)

    items_v1 = [make_item(rng, i) for i in range(N_V1)]
    new_items = [make_item(rng, N_V1 + i) for i in range(N_NEW)]
    by_id_v1 = {it["id"]: it for it in items_v1}

    ids_v1 = [it["id"] for it in items_v1]
    removed_ids = sorted(rng.sample(ids_v1, N_REMOVED))
    removed_set = set(removed_ids)
    common_ids = [i for i in ids_v1 if i not in removed_set]  # 1975

    reannot_ids = set(rng.sample(common_ids, N_REANNOTATED))
    fair_ids = [i for i in common_ids if i not in reannot_ids]  # 1950
    reannot_v2 = {}
    for iid in sorted(reannot_ids):
        old = by_id_v1[iid]
        it = make_item(rng, int(iid[1:]))
        while it["answer"] == old["answer"] or it["question"] == old["question"]:
            it = make_item(rng, int(iid[1:]))  # force both fields to move
        it["id"] = iid
        reannot_v2[iid] = it

    by_id_v2 = {i: reannot_v2.get(i, by_id_v1[i]) for i in common_ids}
    by_id_v2.update({it["id"]: it for it in new_items})
    items_v2 = [by_id_v2[i] for i in common_ids] + new_items  # 2000

    # ---- ckpt_a truth (scored vs v1 wording) ----
    a_correct = set(rng.sample(fair_ids, N_A_CORRECT_FAIR))
    a_correct |= set(rng.sample(sorted(reannot_ids), N_A_CORRECT_REANNOT))
    a_correct |= set(rng.sample(removed_ids, N_A_CORRECT_REMOVED))

    # ---- ckpt_b truth (scored vs v2 wording) ----
    def gold_safe(iid):
        """Truncation-eligible: neither operand equals the gold answer, so
        no fallback extractor can score a truncated row correct."""
        it = by_id_v2[iid]
        return it["answer"] not in (str(it["_a"]), str(it["_b"]))

    # Truncation and bold live in the comparable (fair) set, so they drive the
    # corrected-b score; re-annotated ids stay on the normal template.
    trunc_pool = [i for i in fair_ids if gold_safe(i)]
    trunc_ids = set(rng.sample(trunc_pool, N_TRUNC))
    bold_pool = [i for i in fair_ids if i not in trunc_ids]
    bold_ids = set(rng.sample(bold_pool, N_BOLD))

    trunc_sorted = sorted(trunc_ids)
    bold_sorted = sorted(bold_ids)
    rng.shuffle(trunc_sorted)
    rng.shuffle(bold_sorted)
    b_correct = set(trunc_sorted[:N_TRUNC_RETRY_CORRECT])
    b_correct |= set(bold_sorted[:N_BOLD_CORRECT])
    plain_pool = [i for i in fair_ids if i not in trunc_ids and i not in bold_ids]
    b_correct |= set(rng.sample(plain_pool, N_B_CORRECT_NORMAL_FAIR))
    b_correct |= set(rng.sample(sorted(reannot_ids), N_B_CORRECT_REANNOT))
    b_correct |= set(rng.sample([it["id"] for it in new_items], N_B_CORRECT_NEW))

    # spurious backfill rows are drawn from the fair set, so they are comparable to the main run
    spurious_pool = [
        i
        for i in fair_ids
        if i not in trunc_ids and i not in bold_ids and i in b_correct
    ]
    spurious_ids = sorted(rng.sample(spurious_pool, N_SPURIOUS_BACKFILL))

    # ---- testsets ----
    os.makedirs(os.path.join(outdir, "data"), exist_ok=True)

    def strip(it):
        return {"id": it["id"], "question": it["question"], "answer": it["answer"]}

    # v1 is not shipped; the solver must recover it from git history
    with open(os.path.join(outdir, "_stage_testset_v1.jsonl"), "w") as f:
        for it in items_v1:
            f.write(json.dumps(strip(it)) + "\n")
    # v2 is the shipped testset
    with open(os.path.join(outdir, "data", "testset.jsonl"), "w") as f:
        for it in items_v2:
            f.write(json.dumps(strip(it)) + "\n")

    # ---- ckpt_a predictions (v1 coverage + 40 duplicated rows) ----
    a_rows = []
    for i, it in enumerate(items_v1):
        val = it["answer"] if it["id"] in a_correct else wrong_value(rng, it["answer"])
        ts = f"2026-03-01T02:{(i // 60) % 60:02d}:{i % 60:02d}Z"
        a_rows.append({"id": it["id"], "output": a_output(rng, val), "run_ts": ts})
    row_by_id = {r["id"]: r for r in a_rows}
    dup_pool = sorted(a_correct & set(fair_ids))
    rng.shuffle(dup_pool)
    dup_ids = dup_pool[:N_DUP_ROWS]
    for j, did in enumerate(dup_ids):
        orig = row_by_id[did]
        a_rows.append(
            {
                "id": did,
                "output": orig["output"],
                "run_ts": f"2026-03-01T05:{j // 60:02d}:{j % 60:02d}Z",
            }
        )
    rng.shuffle(a_rows)

    os.makedirs(os.path.join(outdir, "predictions"), exist_ok=True)
    with open(os.path.join(outdir, "predictions", "preds_ckpt_a.jsonl"), "w") as f:
        for r in a_rows:
            f.write(json.dumps(r) + "\n")

    # ---- ckpt_b predictions (v2 coverage; 24 truncated, 130 bold) ----
    b_rows = []
    for i, it in enumerate(items_v2):
        iid = it["id"]
        ts = f"2026-03-08T11:{(i // 60) % 60:02d}:{i % 60:02d}Z"
        if iid in trunc_ids:
            out = truncated_output(rng, it)
        else:
            val = it["answer"] if iid in b_correct else wrong_value(rng, it["answer"])
            out = b_output(rng, val, iid in bold_ids)
        b_rows.append({"id": iid, "output": out, "run_ts": ts})
    with open(os.path.join(outdir, "predictions", "preds_ckpt_b.jsonl"), "w") as f:
        for r in b_rows:
            f.write(json.dumps(r) + "\n")

    # ---- ckpt_b retry backfill (the 24 capped rows alongside spurious rows) ----
    retry_bold = set(trunc_sorted[:N_TRUNC_RETRY_BOLD])  # subset of correct
    retry_rows = []
    for j, iid in enumerate(sorted(trunc_ids)):
        it = by_id_v2[iid]
        val = it["answer"] if iid in b_correct else wrong_value(rng, it["answer"])
        out = (
            f"Reasoning complete. Final answer: **{val}**"
            if iid in retry_bold
            else f"Answer: {val}."
        )
        retry_rows.append(
            {
                "id": iid,
                "output": out,
                "run_ts": f"2026-03-09T09:{j // 60:02d}:{j % 60:02d}Z",
            }
        )
    # 6 spurious backfill rows
    for k, iid in enumerate(spurious_ids):
        it = by_id_v2[iid]
        wrong = wrong_value(rng, it["answer"])
        m = N_TRUNC + k
        retry_rows.append(
            {
                "id": iid,
                "output": f"Answer: {wrong}.",
                "run_ts": f"2026-03-09T10:{m // 60:02d}:{m % 60:02d}Z",
            }
        )
    rng.shuffle(retry_rows)  # interleave so spurious rows aren't trivially last
    with open(
        os.path.join(outdir, "predictions", "preds_ckpt_b_retry.jsonl"), "w"
    ) as f:
        for r in retry_rows:
            f.write(json.dumps(r) + "\n")

    # ---- rerun note that ships next to the backfill ----
    os.makedirs(os.path.join(outdir, "docs"), exist_ok=True)
    with open(os.path.join(outdir, "docs", "ckpt_b_retry_backfill.md"), "w") as f:
        f.write("""# ckpt_b retry backfill (2026-03-09)

Run: `eval-20260309-ckpt_b-retry` (config: `configs/run_ckpt_b_retry.yaml`)

## Why this rerun exists

The 2026-03-08 `ckpt_b` eval (`eval-20260308-ckpt_b`) was launched with
`max_tokens` lowered from 1024 to 256. A number of items needed more than 256
tokens of reasoning and were cut off mid-generation, so their cached outputs in
`predictions/preds_ckpt_b.jsonl` end abruptly with no final-answer line.

On 2026-03-09 we re-ran those items on the same checkpoint (`ckpt_b`) and the
same testset (v2), with `max_tokens` restored to 1024. The regenerated rows are
in `preds_ckpt_b_retry.jsonl`, one JSON object per line
(`{"id", "output", "run_ts"}`), same schema as the main prediction file.

## Coverage

The backfill covers **exactly the 24 rows that hit the 256-token cap**.
Rows that completed normally on 03-08 were not re-generated. To apply the
backfill, replace each main-run row by `id` with its row here.

## Not re-scored

The published dashboard was scored against the 03-08 outputs and has **not** been
recomputed against this backfill. For the most accurate evaluation, substitute these
backfill rows for the truncated rows in `preds_ckpt_b.jsonl` and re-run the scoring harness.
""")

    # ---- testset changelog ----
    with open(os.path.join(outdir, "docs", "testset_changelog.md"), "w") as f:
        f.write("""# arithmetic-QA testset changelog

- 2026-02-10 (v1): initial 2000-item release (`q0000..q1999`).
- 2026-03-04 (v2): annotation review. 25 item IDs were retired as ambiguous
  and 25 freshly authored items with new IDs were added in their place, keeping the suite at 2000 items.   
  A separate set of 25 items were re-annotated in place: their question text and gold answer were
  both replaced with a different problem (same id, different content).
""")

    # ---- run configs ----
    os.makedirs(os.path.join(outdir, "configs"), exist_ok=True)
    with open(os.path.join(outdir, "configs", "run_ckpt_a.yaml"), "w") as f:
        f.write("""# eval run configuration — ckpt_a
run_id: eval-20260301-ckpt_a
model_checkpoint: ckpt_a
suite: arithmetic-qa
testset_rev: v1
temperature: 0.0
top_p: 1.0
max_tokens: 1024
n_samples_per_item: 1
""")
    with open(os.path.join(outdir, "configs", "run_ckpt_b.yaml"), "w") as f:
        f.write("""# eval run configuration — ckpt_b
run_id: eval-20260308-ckpt_b
model_checkpoint: ckpt_b
suite: arithmetic-qa
testset_rev: v2
temperature: 0.0
top_p: 1.0
max_tokens: 256
n_samples_per_item: 1
""")
    with open(os.path.join(outdir, "configs", "run_ckpt_b_retry.yaml"), "w") as f:
        f.write("""# eval run configuration — ckpt_b retry
run_id: eval-20260309-ckpt_b-retry
model_checkpoint: ckpt_b
suite: arithmetic-qa
testset_rev: v2
temperature: 0.0
top_p: 1.0
max_tokens: 1024
n_samples_per_item: 1
""")

    # ---- sanity assertions on constructed ground truth ----
    common_set = set(common_ids)
    fair_set = set(fair_ids)
    assert len(items_v2) == N_V1 and len(common_ids) == N_COMMON
    assert len(fair_ids) == N_FAIR and len(reannot_ids) == N_REANNOTATED
    assert reannot_ids <= common_set and fair_set.isdisjoint(reannot_ids)
    assert len(a_rows) == N_V1 + N_DUP_ROWS
    assert len(b_rows) == N_V1
    assert len(retry_rows) == N_TRUNC + N_SPURIOUS_BACKFILL
    assert len(a_correct & fair_set) == N_A_CORRECT_FAIR
    assert len(a_correct & reannot_ids) == N_A_CORRECT_REANNOT
    assert len(a_correct & removed_set) == N_A_CORRECT_REMOVED
    assert len(dup_ids) == N_DUP_ROWS
    assert all(d in a_correct and d in fair_set for d in dup_ids)
    assert len(trunc_ids & bold_ids) == 0
    assert trunc_ids <= fair_set and bold_ids <= fair_set
    assert len(b_correct & trunc_ids) == N_TRUNC_RETRY_CORRECT
    assert len(b_correct & bold_ids) == N_BOLD_CORRECT
    assert len(b_correct & fair_set) == N_B_CORRECT_FAIR
    assert len(b_correct & reannot_ids) == N_B_CORRECT_REANNOT
    assert len(b_correct - common_set) == N_B_CORRECT_NEW
    # spurious backfill: 6 non-truncated, comparable, correct-in-main ids;
    # their backfilled rows are wrong, so substituting them flips 6 correct
    # rows to incorrect. They must NOT be in the truncated set.
    assert len(spurious_ids) == N_SPURIOUS_BACKFILL
    assert set(spurious_ids).isdisjoint(trunc_ids)
    assert set(spurious_ids).isdisjoint(bold_ids)
    assert all(i in fair_set and i in b_correct for i in spurious_ids)
    retry_id_set = {r["id"] for r in retry_rows}
    assert len(retry_id_set) == len(retry_rows), "duplicate id in backfill"
    assert trunc_ids <= retry_id_set, "backfill must cover all truncated rows"
    assert retry_id_set - trunc_ids == set(spurious_ids)
    for r in retry_rows:
        if r["id"] in spurious_ids:
            it = by_id_v2[r["id"]]
            assert it["answer"] not in re.findall(r"-?\d+", r["output"]), r["id"]
    # re-annotation: exactly the 25 re-annotated ids move gold AND question
    # between v1 and v2; every other common id is stable across the revisions.
    gold_v1 = {it["id"]: it["answer"] for it in items_v1}
    gold_v2 = {it["id"]: it["answer"] for it in items_v2}
    q_v1 = {it["id"]: it["question"] for it in items_v1}
    q_v2 = {it["id"]: it["question"] for it in items_v2}
    for i in common_ids:
        if i in reannot_ids:
            assert gold_v1[i] != gold_v2[i] and q_v1[i] != q_v2[i], i
        else:
            assert gold_v1[i] == gold_v2[i] and q_v1[i] == q_v2[i], i
    assert sum(1 for i in common_ids if gold_v1[i] != gold_v2[i]) == N_REANNOTATED
    # Truncated outputs: no marker, no digit token equal to gold, near-cap length.
    marker = re.compile(r"answer\s*(?:is|:)", re.IGNORECASE)
    for r in b_rows:
        if r["id"] in trunc_ids:
            assert not marker.search(r["output"]), r["id"]
            gold = by_id_v2[r["id"]]["answer"]
            assert gold not in re.findall(r"-?\d+", r["output"]), r["id"]
            assert len(r["output"]) > 900, r["id"]
        else:
            assert marker.search(r["output"]), r["id"]
    for r in a_rows:
        assert re.search(r"answer is\s*-?\d", r["output"], re.IGNORECASE)

    print(
        f"[generate_data] v1={len(items_v1)} v2={len(items_v2)} "
        f"common={len(common_ids)} fair={len(fair_ids)} "
        f"reannot={len(reannot_ids)} preds_a={len(a_rows)} "
        f"preds_b={len(b_rows)} retries={len(retry_rows)}"
    )


if __name__ == "__main__":
    main(sys.argv[1])
