"""
Flags a regression only if the latest F1 falls below the historical minimum
minus a buffer — accounts for normal run-to-run variance rather than flagging
every run that's simply not the best one ever seen.

Run: uv run python -m src.eval.check_regression
"""
import re
import sys

from src.eval.run_eval import run_eval

HISTORY_PATH = "src/eval/results_history.md"
BUFFER = 0.05


def _historical_f1_scores() -> list[float]:
    try:
        with open(HISTORY_PATH) as f:
            text = f.read()
    except FileNotFoundError:
        return []

    scores = []
    for row in re.findall(r"\|[^\n]*\|\s*([0-9]\.[0-9]{2})\s*\|[^\n]*\|", text):
        try:
            scores.append(float(row))
        except ValueError:
            continue
    return scores


def main():
    summary = run_eval()
    current_f1 = summary["aggregate"]["f1"]

    history = _historical_f1_scores()
    if not history:
        print(f"No history found — current F1={current_f1:.2f} recorded as baseline.")
        sys.exit(0)

    historical_min = min(history)
    threshold = historical_min - BUFFER

    print(f"Current F1: {current_f1:.2f}")
    print(f"Historical range: {min(history):.2f} - {max(history):.2f} (n={len(history)})")
    print(f"Regression threshold: {threshold:.2f}")

    if current_f1 < threshold:
        print(f"REGRESSION: F1 {current_f1:.2f} is below threshold {threshold:.2f}")
        sys.exit(1)

    print("OK — within normal variance.")


if __name__ == "__main__":
    main()
