"""Runs the pipeline against the tuning eval set and scores the result."""
import json
import os

from rich.console import Console
from rich.table import Table

from src.agent.graph import run_review
from src.agent.prompts import PROMPT_VERSION
from src.eval.metrics import match_findings

console = Console()

TEST_SET_DIR = os.path.join(os.path.dirname(__file__), "test_set")
MANIFEST_PATH = os.path.join(TEST_SET_DIR, "manifest.json")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "eval_results.json")


def run_eval():
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    table = Table(title=f"Eval results (prompt {PROMPT_VERSION})")
    table.add_column("Snippet")
    table.add_column("TP")
    table.add_column("FP")
    table.add_column("FN")
    table.add_column("Precision")
    table.add_column("Recall")
    table.add_column("F1")

    all_results = []
    agg_tp = agg_fp = agg_fn = 0

    for snippet in manifest["snippets"]:
        snippet_path = os.path.join(TEST_SET_DIR, snippet["file"])
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

        all_results.append({
            "id": snippet["id"],
            "tp": result.true_positives,
            "fp": result.false_positives,
            "fn": result.false_negatives,
            "precision": result.precision,
            "recall": result.recall,
            "f1": result.f1,
            "findings": findings,
        })

    console.print(table)

    total_p = agg_tp / (agg_tp + agg_fp) if (agg_tp + agg_fp) else 1.0
    total_r = agg_tp / (agg_tp + agg_fn) if (agg_tp + agg_fn) else 1.0
    total_f1 = 2 * total_p * total_r / (total_p + total_r) if (total_p + total_r) else 0.0

    console.print(
        f"\n[bold]Aggregate[/bold]: precision={total_p:.2f} recall={total_r:.2f} f1={total_f1:.2f}"
    )

    summary = {
        "prompt_version": PROMPT_VERSION,
        "aggregate": {"precision": total_p, "recall": total_r, "f1": total_f1},
        "per_snippet": all_results,
    }
    with open(RESULTS_PATH, "w") as f:
        json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    run_eval()
