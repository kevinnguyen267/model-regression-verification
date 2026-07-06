# Run Report

## Oracle Result

Command:

```
harbor run -p model-regression-verification/ -a oracle
```

Result:

```
{
  "reward": 1.0
}
[PASS] findings_present: corrected_score_a=78.0 corrected_score_b=79.49
[PASS] corrected_score_a_correct: reported=78.0, gt=78.0, tol=0.05
[PASS] corrected_score_b_correct: reported=79.49, gt=79.49, tol=0.05
[PASS] corrected_score_a_reproducible: agent harness on corrected-a rows = 78.0 vs reported 78.0
[PASS] corrected_score_b_reproducible: agent harness on corrected-b rows = 79.49 vs reported 79.49
```

## Target Model Results

Harnesses: `Terminus-2, Codex`

Model: `GPT-5.5 (high)`

Commands:

```
harbor run -p model-regression-verification/ -a terminus-2 -m openrouter/openai/gpt-5.5 --ak reasoning_effort=high --n-attempts 4 -n 4
```

```
harbor run -p model-regression-verification/ -a codex -m openai/gpt-5.5
```

Results from Terminus-2 (0/4 successes):

```
{
  "reward": 0.0
}
[PASS] findings_present: corrected_score_a=78.05 corrected_score_b=79.1
[PASS] corrected_score_a_correct: reported=78.05, gt=78.0, tol=0.05
[FAIL] corrected_score_b_correct: reported=79.1, gt=79.49, tol=0.05
[FAIL] corrected_score_a_reproducible: agent harness on corrected-a rows = 76.05 vs reported 78.05
[FAIL] corrected_score_b_reproducible: agent harness on corrected-b rows = 77.5 vs reported 79.1
```

```
{
  "reward": 0.0
}
[PASS] findings_present: corrected_score_a=76.05 corrected_score_b=79.1
[FAIL] corrected_score_a_correct: reported=76.05, gt=78.0, tol=0.05
[FAIL] corrected_score_b_correct: reported=79.1, gt=79.49, tol=0.05
[PASS] corrected_score_a_reproducible: agent harness on corrected-a rows = 76.05 vs reported 76.05
[FAIL] corrected_score_b_reproducible: agent harness on corrected-b rows = 77.5 vs reported 79.1
```

```
{
  "reward": 0.0
}
[PASS] findings_present: corrected_score_a=76.05 corrected_score_b=79.1
[FAIL] corrected_score_a_correct: reported=76.05, gt=78.0, tol=0.05
[FAIL] corrected_score_b_correct: reported=79.1, gt=79.49, tol=0.05
[PASS] corrected_score_a_reproducible: agent harness on corrected-a rows = 76.05 vs reported 76.05
[FAIL] corrected_score_b_reproducible: agent harness on corrected-b rows = 77.5 vs reported 79.1
```

```
{
  "reward": 0.0
}
[PASS] findings_present: corrected_score_a=78.48 corrected_score_b=79.1
[FAIL] corrected_score_a_correct: reported=78.48, gt=78.0, tol=0.05
[FAIL] corrected_score_b_correct: reported=79.1, gt=79.49, tol=0.05
[FAIL] corrected_score_a_reproducible: agent harness on corrected-a rows = 78.0 vs reported 78.48
[FAIL] corrected_score_b_reproducible: agent harness on corrected-b rows = 79.49 vs reported 79.1
```

Results from Codex (1/2 successes):
```
{
  "reward": 0.0
}
[PASS] findings_present: corrected_score_a=77.01 corrected_score_b=79.49
[FAIL] corrected_score_a_correct: reported=77.01, gt=78.0, tol=0.05
[PASS] corrected_score_b_correct: reported=79.49, gt=79.49, tol=0.05
[FAIL] corrected_score_a_reproducible: agent harness on corrected-a rows = 76.05 vs reported 77.01
[FAIL] corrected_score_b_reproducible: agent harness on corrected-b rows = 77.5 vs reported 79.49
```

```
{
  "reward": 1.0
}
[PASS] findings_present: corrected_score_a=78.0 corrected_score_b=79.49
[PASS] corrected_score_a_correct: reported=78.0, gt=78.0, tol=0.05
[PASS] corrected_score_b_correct: reported=79.49, gt=79.49, tol=0.05
[PASS] corrected_score_a_reproducible: agent harness on corrected-a rows = 78.0 vs reported 78.0
[PASS] corrected_score_b_reproducible: agent harness on corrected-b rows = 79.49 vs reported 79.49
```

## Failure analysis

1. There are no cases where the model gets both checkpoint scores correct but fails the reproducibility check (using the patched score.py). This validates the following claim: in all 5 failed cases, the reported final scores are fabricated or computed with different logic than what was used to patch the script. In most cases, the model anchors off of the scores provided in the dashboard, which yields an incorrect answer.

2. In all 5 failed cases, the model explicitly recognizes that the 25 in-place re-annotations for testset v1 cause an unfair comparison. However, unlike the single success case, it either doesn't look in the git history (or looks too shallow, only at the commit messages, finds nothing, and gives up) to find out which 25 items are poisoned. It moves on and makes the claim that the common dataset consists of 1975 (instead of 1950) items.

3. Building off of the above bullet, the model's *laziness* involving the git history often comes after the regression claim has already been shown to be false (due to the other confounds), which makes the model less inclined to continue searching. A natural follow up would be exploring this git archaeology failure mode in a shorter horizon task. 

## Fairness audit

- **Everything is discoverable in-workspace.** The changelog documents the
  re-annotation, the backfill note documents the truncation, the configs show the
  `max_tokens` drop, and git history contains both the extractor's evolution and
  the v1 testset. No confound requires outside knowledge or guessing.
- **The one deceptive element is verifiable.** The backfill note's "exactly 24
  rows" claim is false, but the truncated rows are unambiguous in the data
  (mid-word cutoff, no answer marker), so the claim can be checked rather than
  trusted.
- **Tolerance is calibrated.** `TOL = 0.05` is below one item's weight (~0.0513
  points on 1950 rows), so rounding passes and any real one-item error fails.

This task is proven to be difficult (4/4 failures using Terminus-2 and 1/2 failures using Codex) but possible for GPT-5.5-high (1/2 successes using Codex). The trajectory of the success case matches the oracle solver.

## Additional Comments
4 trials were additionally run using `Terminus-2` and `Claude Opus 4.7`. The success rate was similarly 0/4.

Notably, the total cost of a single failure was ~$0.50. `GPT-5.5-high` and `Terminus-2` used 3x the cost for a failure, while using `Codex` used 2x the cost for a failure *or* success.