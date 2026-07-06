#!/usr/bin/env python3
import json
import re
import sys

_ANSWER_RE = re.compile(r"answer(?:\s+is)?\s*:?\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def extract_answer(text):
    """Extract the model's final numeric answer from its raw output text.

    Handles every answer-bearing style present in the cached runs:
      - "the answer is <value>"                     (ckpt_a era template)
      - "Answer: <value>" / "Answer: <value>."      (ckpt_b era template)
      - "Final answer: **<value>**"                 (ckpt_b markdown-bold)
    Markdown emphasis is stripped before matching. A last-number fallback
    covers residual free-form outputs; truly answer-free text returns None.
    """
    t = text.replace("**", "").replace("*", "")
    m = _ANSWER_RE.search(t)
    if m:
        return m.group(1)
    nums = _NUMBER_RE.findall(t)
    return nums[-1] if nums else None


def score(preds_path, testset_path):
    gold = {}
    with open(testset_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            gold[r["id"]] = r["answer"]

    n = 0
    correct = 0
    with open(preds_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            n += 1
            ext = extract_answer(row["output"])
            try:
                if ext is not None and float(ext) == float(gold[row["id"]]):
                    correct += 1
            except (ValueError, KeyError):
                pass
    acc = round(100.0 * correct / n, 2) if n else 0.0
    return {"accuracy": acc, "n": n}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.stderr.write("usage: score.py <predictions.jsonl> <testset.jsonl>\n")
        sys.exit(2)
    print(json.dumps(score(sys.argv[1], sys.argv[2])))
