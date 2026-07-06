# Model Regression Validation

## Overview

The agent lands in an offline workspace (`/app`) where a
dashboard reports a regression on an arithmetic-QA suite: `ckpt_a` scored 78.48 and `ckpt_b` scored 73.35. The regression is a measurement artifact, and once the comparison is made fair, `ckpt_b`
actually **improves** (true scores are 78.00 and 79.49). The agent must audit the cached runs, patch
the scoring harness, and write the corrected apples-to-apples accuracies to
`/app/findings.json`.

Four planted confounds must all be found and corrected:

1. **Extractor drift**: `score.py` at HEAD only matches `Answer: <value>`. All
   2040 `ckpt_a` outputs use the legacy `the answer is <value>` phrasing (0
   extraction hits), and 130 `ckpt_b` rows use a markdown-bold
   `Final answer: **<value>**` template. Git history shows the legacy pattern and
   the last-number fallback being removed over successive commits, and a pass over the predictions reveals the different answer formats. 
2. **Duplicate rows**: `preds_ckpt_a.jsonl` contains 40 duplicated ids (all on
   correct items), inflating `ckpt_a` under the harness's score-every-row contract. Clearly shown in the provided dashboard.
3. **Testset revision**: retired 25 ids, added 25 new ids, and re-annotated
   25 ids in place (same id, different question *and* gold). The two checkpointed runs used
   different revisions, so only the 1950-item stable common set is comparable.
   v1 is not shipped; it must be recovered from git history (`HEAD~6:testset_v1.jsonl`). These revisions are documented and provided to the model in `docs/testset_changelog.md`.
4. **Truncation + spurious backfill**: the `ckpt_b` run was launched with
   `max_tokens: 256` (provided configs show the drop from 1024); 24 rows are cut off
   mid-word with no answer. A documented retry backfill is given to the model at `docs/ckpt_b_retry_backfill.md` but falsely claims that it only contains the truncated rows. Instead, it contains 30 rows: the 24 truncated ids plus 6 spurious rows for non-truncated ids whose backfilled outputs are *wrong*. Only verified-truncated rows should be substituted, which is described in the document.

## Skills tested

The oracle at `solution/` exercises, in order:

- **Data hygiene / diagnostics**: count duplicate ids and measure extraction
  coverage against the live regex before trusting any score.
- **Git archaeology**: walk the harness history to understand extractor drift and
  recover the unshipped v1 testset from an old commit's tree.
- **Cross-referencing docs against data**: the changelog and backfill note flag
  the re-annotation and truncation, but the backfill's "exactly 24 rows" claim is
  false and must be checked empirically (marker-free, near-cap-length outputs).
- **Fair-comparison methodology**: restrict both runs to the id-level
  intersection, drop re-annotated ids, dedupe, substitute only verified retries.
- **Patching**: extend `extract_answer` to cover all three answer
  styles without breaking the harness CLI contract.

## Verifier design

The verifier at `tests/` yields a binary reward (1.0 for all conditions met, else 0.0).

- **Findings check**: `/app/findings.json` exists and has numeric `corrected_score_a` and
  `corrected_score_b` matching hard-coded ground truth (78.00 / 79.49) within
  `TOL = 0.05`. One item in the 1950-row set is worth ~0.0513 accuracy points, so
  the tolerance absorbs 2-decimal rounding while any single-item error fails.
- **Anti-fabrication check**: the canonical corrected row sets (`a_corr`,
  `b_corr`) are embedded in the verifier and re-scored through the
  *agent's* patched `/app/repo/score.py` CLI against the pristine testset. The
  agent's own harness must reproduce the reported numbers, so writing the right
  numbers without a working patch fails.

## Limitations

- **All-or-nothing reward**: no partial credit for finding a subset of the
  confounds, so scores don't distinguish "missed one confound" from "did nothing."
- **Simple data**: answer styles are three simple exact templates; the patch to `/app/repo/score.py` can be found with one command.

## Additional Notes
Everything in this repository was created from scratch for this task.