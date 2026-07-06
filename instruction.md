There's a /app/dashboard.csv file that shows the latest model checkpoint performing worse than the previous checkpoint. The run configs can be found in configs/. The scores are computed from the /app/repo/score.py script. 

Usage: python3 score.py <predictions.jsonl> <testset.jsonl>

All predictions and testsets are cached in predictions/ and data/. No additional reruns are necessary.
The eval team documented any notable changes in docs/.

Your task is to verify whether the regression statement is fair and valid. Report a single JSON object with 2 fields, corrected_score_a and corrected_score_b, as accuracies rounded to 2 decimal places, to /app/findings.json. Patch /app/repo/score.py if necessary.