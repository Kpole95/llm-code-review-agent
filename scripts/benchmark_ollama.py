"""
Benchmark all installed Ollama models against your snippet sets.
Saves results after every run — safe to interrupt and resume.

Usage:
    uv run python scripts/benchmark_ollama.py                  # all snippets
    uv run python scripts/benchmark_ollama.py --set fixtures   # tests/fixtures only
    uv run python scripts/benchmark_ollama.py --set test_set   # tuning set only
    uv run python scripts/benchmark_ollama.py --set holdout    # holdout set only
    uv run python scripts/benchmark_ollama.py --resume         # skip already-done runs
    uv run python scripts/benchmark_ollama.py --dry-run        # show plan, don't run
    uv run python scripts/benchmark_ollama.py --models llama3.1:8b qwen3:8b
"""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import httpx

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
RESULTS_FILE = "benchmark_results.json"

SNIPPET_SETS = {
    "fixtures": [
        p for p in Path("tests/fixtures").rglob("*")
        if p.suffix in {".py", ".js", ".ts", ".go", ".java"}
        and "__pycache__" not in str(p)
    ],
    "test_set": [
        p for p in Path("src/eval/test_set/snippets").rglob("*")
        if p.suffix in {".py", ".js", ".ts", ".go", ".java"}
        and "__pycache__" not in str(p)
    ],
    "holdout": [
        p for p in Path("src/eval/holdout/snippets").rglob("*")
        if p.suffix in {".py", ".js", ".ts", ".go", ".java"}
        and "__pycache__" not in str(p)
    ],
}


def get_installed_models() -> list[str]:
    try:
        resp = httpx.get(f"{OLLAMA_BASE}/api/tags", timeout=10.0)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]
    except Exception as e:
        print(f"Cannot reach Ollama at {OLLAMA_BASE}: {e}")
        return []


def load_results() -> dict:
    if Path(RESULTS_FILE).exists():
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return {}


def save_results(results: dict):
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)


def run_key(model: str, filepath: str) -> str:
    return f"{model}|{filepath}"


def run_review(model: str, filepath: str) -> dict:
    env = os.environ.copy()
    env["MODEL_PROVIDER"] = "ollama"
    env["OLLAMA_MODEL"] = model
    env["OLLAMA_BASE_URL"] = OLLAMA_BASE

    start = time.time()
    try:
        result = subprocess.run(
            ["uv", "run", "python", "-m", "src.cli", "review", filepath],
            capture_output=True, text=True, env=env, timeout=600
        )
        elapsed = round(time.time() - start, 1)
        output = result.stdout + result.stderr
        findings_count = output.count("Line ")
        return {
            "model": model,
            "file": filepath,
            "findings": findings_count,
            "elapsed": elapsed,
            "error": result.stderr[-300:] if result.returncode != 0 else "",
            "output": result.stdout[:2000],
        }
    except subprocess.TimeoutExpired:
        return {
            "model": model, "file": filepath,
            "findings": 0, "elapsed": 300.0,
            "error": "TIMEOUT (>300s)", "output": "",
        }
    except Exception as e:
        return {
            "model": model, "file": filepath,
            "findings": 0, "elapsed": round(time.time() - start, 1),
            "error": str(e), "output": "",
        }


def print_summary(results: dict, files: list, models: list[str]):
    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)

    print(f"\n{'Model':<35} {'Files':>6} {'Findings':>10} {'Avg (s)':>8} {'Errors':>7}")
    print("-" * 70)

    for model in models:
        model_results = [v for v in results.values() if v["model"] == model]
        if not model_results:
            print(f"{model:<35} {'—':>6} {'—':>10} {'—':>8} {'—':>7}")
            continue
        total_findings = sum(r["findings"] for r in model_results)
        errors = sum(1 for r in model_results if r["error"])
        times = [r["elapsed"] for r in model_results if not r["error"]]
        avg_time = round(sum(times) / len(times), 1) if times else 0
        print(f"{model:<35} {len(model_results):>6} {total_findings:>10} {avg_time:>8} {errors:>7}")

    print("\n── Findings per file ──")
    col_width = 9
    print(f"{'File':<42}", end="")
    for m in models:
        short = m.split(":")[0][-8:]
        print(f"{short:>{col_width}}", end="")
    print()
    print("-" * (42 + col_width * len(models)))

    for f in sorted(files, key=str):
        fname = str(f)[-38:]
        print(f"{fname:<42}", end="")
        for model in models:
            key = run_key(model, str(f))
            if key in results:
                r = results[key]
                val = "ERR" if r["error"] else str(r["findings"])
            else:
                val = "—"
            print(f"{val:>{col_width}}", end="")
        print()

    print("\n" + "=" * 80)
    print(f"Full results saved to {RESULTS_FILE}")
    print(f"To see a run's output:")
    print(f"  python -c \"import json; r=json.load(open('{RESULTS_FILE}')); print(r['<model>|<file>']['output'])\"")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=["fixtures", "test_set", "holdout", "all"],
                        default="all")
    parser.add_argument("--resume", action="store_true",
                        help="Skip runs already saved in benchmark_results.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show plan without running")
    parser.add_argument("--models", nargs="+",
                        help="Only test these models")
    args = parser.parse_args()

    # Collect files
    if args.set == "all":
        files = sorted(set(f for s in SNIPPET_SETS.values() for f in s))
    else:
        files = sorted(SNIPPET_SETS[args.set])
    files = [f for f in files if f.exists()]

    if not files:
        print(f"No files found for --set {args.set}")
        return

    # Collect models
    print("Checking installed Ollama models...")
    installed = get_installed_models()
    if not installed:
        return

    if args.models:
        models = [m for m in args.models if any(m in i for i in installed)]
        missing = [m for m in args.models if m not in models]
        if missing:
            print(f"Not installed (skipping): {', '.join(missing)}")
    else:
        models = installed

    if not models:
        print("No matching models installed.")
        return

    # Load existing results
    results = load_results() if args.resume else {}

    # Work out what to run
    todo = [
        (model, str(f), run_key(model, str(f)))
        for model in models
        for f in files
        if run_key(model, str(f)) not in results
    ]

    total = len(models) * len(files)
    skipped = total - len(todo)

    print(f"\nModels   : {', '.join(models)}")
    print(f"Files    : {len(files)} ({args.set})")
    print(f"Total    : {total} runs")
    if skipped:
        print(f"Skipping : {skipped} (already done)")
    print(f"To run   : {len(todo)}")

    est_secs = len(todo) * 90
    if est_secs >= 3600:
        print(f"Est. time: ~{est_secs//3600}h {(est_secs%3600)//60}m (CPU estimate)")
    else:
        print(f"Est. time: ~{est_secs//60} minutes (CPU estimate)")

    if args.dry_run:
        print("\n[dry-run] Remove --dry-run to execute.")
        return

    if not todo:
        print("\nAll runs already complete. Run without --resume to redo them.")
        print_summary(results, files, models)
        return

    print()
    for i, (model, filepath, key) in enumerate(todo, 1):
        fname = Path(filepath).name
        print(f"[{i}/{len(todo)}] {model} → {fname}...", end=" ", flush=True)
        result = run_review(model, filepath)
        results[key] = result
        save_results(results)
        if result["error"]:
            print(f"ERROR — {result['error'][:60]}")
        else:
            print(f"{result['findings']} finding(s) in {result['elapsed']}s")

    print_summary(results, files, models)


if __name__ == "__main__":
    main()