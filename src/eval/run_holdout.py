"""
Runs the pipeline against the hold-out set — snippets never used during
development or tuning, for an unbiased accuracy estimate.

Run: uv run python -m src.eval.run_holdout
"""
import json
import os

from rich.console import Console
from rich.table import Table

from src.agent.graph import run_review
from src.eval.metrics import match_findings

console = Console()
HOLDOUT_DIR = os.path.join(os.path.dirname(__file__), "holdout")
MANIFEST_PATH = os.path.join(HOLDOUT_DIR, "manifest.json")


def run_holdout():
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    table = Table(title="Hold-out eval (unseen snippets)")
    table.add_column("Snippet")
    table.add_column("TP")
    table.add_column("FP")
    table.add_column("FN")
    table.add_column("Precision")
    table.add_column("Recall")
    table.add_column("F1")

    agg_tp = agg_fp = agg_fn = 0

    for snippet in manifest["snippets"]:
        snippet_path = os.path.join(HOLDOUT_DIR, snippet["file"])
        with open(snippet_path) as f:
            content = f.read()

        findings = run_review([{
            "path": snippet["file"],
            "content": content,
            "language": snippet["language"],
        }])

        result = match_findings(findings, snippet["expected_findings"])
        agg_tp += result.true_positives
        agg_fp += result.false_positives
        agg_fn += result.false_negatives

        table.add_row(
            snippet["id"],
            str(result.true_positives),
            str(result.false_positives),
            str(result.false_negatives),
            f"{result.precision:.2f}",
            f"{result.recall:.2f}",
            f"{result.f1:.2f}",
        )

    console.print(table)

    total_p = agg_tp / (agg_tp + agg_fp) if (agg_tp + agg_fp) else 1.0
    total_r = agg_tp / (agg_tp + agg_fn) if (agg_tp + agg_fn) else 1.0
    total_f1 = 2 * total_p * total_r / (total_p + total_r) if (total_p + total_r) else 0.0
    console.print(
        f"\n[bold]Hold-out aggregate[/bold]: precision={total_p:.2f} recall={total_r:.2f} f1={total_f1:.2f}"
    )

    with open(os.path.join(HOLDOUT_DIR, "holdout_results.json"), "w") as f:
        json.dump({"aggregate": {"precision": total_p, "recall": total_r, "f1": total_f1}}, f, indent=2)

    return {"precision": total_p, "recall": total_r, "f1": total_f1}


if __name__ == "__main__":
    run_holdout()
