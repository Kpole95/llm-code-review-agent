"""Logs eval runs to MLflow as a queryable history of experiments."""
import mlflow

from src.agent.prompts import PROMPT_VERSION
from src.config import settings
from src.eval.run_eval import RESULTS_PATH, run_eval


def log_eval_run():
    if settings.mlflow_tracking_uri:
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)

    mlflow.set_experiment("llm-code-review-agent")

    with mlflow.start_run(run_name=f"eval-{PROMPT_VERSION}"):
        mlflow.log_param("prompt_version", PROMPT_VERSION)
        mlflow.log_param("model", "claude-haiku-4-5")
        mlflow.log_param("rag_k", 3)

        summary = run_eval()

        agg = summary["aggregate"]
        mlflow.log_metric("precision", agg["precision"])
        mlflow.log_metric("recall", agg["recall"])
        mlflow.log_metric("f1", agg["f1"])

        for snippet in summary["per_snippet"]:
            prefix = snippet["id"]
            mlflow.log_metric(f"{prefix}_precision", snippet["precision"])
            mlflow.log_metric(f"{prefix}_recall", snippet["recall"])
            mlflow.log_metric(f"{prefix}_f1", snippet["f1"])

        mlflow.log_artifact(RESULTS_PATH)

    print(f"Logged run: precision={agg['precision']:.2f} recall={agg['recall']:.2f} f1={agg['f1']:.2f}")


if __name__ == "__main__":
    log_eval_run()
