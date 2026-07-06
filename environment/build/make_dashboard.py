#!/usr/bin/env python3
import csv
import importlib.util
import os
import subprocess
import sys
import tempfile


def harness_at_rev(repo, rev, label, tmpdir):
    src = subprocess.check_output(
        ["git", "-C", repo, "show", f"{rev}:score.py"], text=True
    )
    path = os.path.join(tmpdir, f"score_{label.replace('.', '_')}.py")
    with open(path, "w") as f:
        f.write(src)
    spec = importlib.util.spec_from_file_location(f"score_{label}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def file_at_rev(repo, rev, repo_path, out_path):
    """Materialize a repo file as it existed at <rev> into out_path."""
    src = subprocess.check_output(
        ["git", "-C", repo, "show", f"{rev}:{repo_path}"], text=True
    )
    with open(out_path, "w") as f:
        f.write(src)
    return out_path


def main(appdir):
    repo = os.path.join(appdir, "repo")
    preds_a = os.path.join(appdir, "predictions", "preds_ckpt_a.jsonl")
    preds_b = os.path.join(appdir, "predictions", "preds_ckpt_b.jsonl")
    testset_v2 = os.path.join(appdir, "data", "testset.jsonl")

    with tempfile.TemporaryDirectory() as td:
        h_a = harness_at_rev(repo, "HEAD~6", "commit4", td)
        h_b = harness_at_rev(repo, "HEAD", "head", td)
        testset_v1 = file_at_rev(
            repo, "HEAD~6", "testset_v1.jsonl", os.path.join(td, "testset_v1.jsonl")
        )
        res_a = h_a.score(preds_a, testset_v1)
        res_b = h_b.score(preds_b, testset_v2)

    assert res_a == {"accuracy": 78.48, "n": 2040}, res_a
    assert res_b == {"accuracy": 73.35, "n": 2000}, res_b

    out = os.path.join(appdir, "dashboard.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            ["checkpoint", "testset_rev", "run_date", "n_rows_scored", "accuracy_pct"]
        )
        w.writerow(
            ["ckpt_a", "v1", "2026-03-01", res_a["n"], f"{res_a['accuracy']:.2f}"]
        )
        w.writerow(
            ["ckpt_b", "v2", "2026-03-08", res_b["n"], f"{res_b['accuracy']:.2f}"]
        )
    print(f"[make_dashboard] a={res_a} b={res_b} -> {out}")


if __name__ == "__main__":
    main(sys.argv[1])
