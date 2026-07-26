"""Command-line entry point.

Usage:
    uv run python -m src.cli review <path>
    uv run python -m src.cli review <path> --provider deepseek
    uv run python -m src.cli review <path> --provider groq --model llama-3.1-70b-versatile
    uv run python -m src.cli review <path> --provider openai --model gpt-4o
"""
import argparse
import os

from rich.console import Console

from src.agent.graph import run_review
from src.parsing.pr_loader import load_path

console = Console()

_SEVERITY_COLOR = {
    "low": "cyan",
    "medium": "yellow",
    "high": "red",
    "critical": "bold red",
}

PROVIDERS = ["anthropic", "openai", "deepseek", "groq", "gemini", "ollama"]


def review_command(path: str, provider: str | None, model: str | None):
    # Override provider/model via env so llm_client picks them up at import
    if provider:
        os.environ["MODEL_PROVIDER"] = provider
    if model:
        # Set the right model env var for the chosen provider
        p = (provider or os.getenv("MODEL_PROVIDER", "anthropic")).lower()
        env_key = {
            "openai": "OPENAI_MODEL",
            "deepseek": "DEEPSEEK_MODEL",
            "groq": "GROQ_MODEL",
            "gemini": "GEMINI_MODEL",
            "ollama": "OLLAMA_MODEL",
            "anthropic": "ANTHROPIC_MODEL",
        }.get(p, "ANTHROPIC_MODEL")
        os.environ[env_key] = model

    # Import after env is set so the backend builds with the right config
    import importlib
    import src.agent.llm_client as lc
    importlib.reload(lc)

    active_provider = os.getenv("MODEL_PROVIDER", "anthropic")
    console.print(f"[dim]Provider: {active_provider}[/dim]")

    try:
        files = load_path(path)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return

    if not files:
        console.print(f"[yellow]No supported files found at {path}[/yellow]")
        return

    console.print(f"Reviewing {len(files)} file(s) in [bold]{path}[/bold]...\n")
    findings = run_review(files)

    if not findings:
        console.print("[green]No issues found.[/green]")
        return

    by_file: dict[str, list[dict]] = {}
    for finding in findings:
        by_file.setdefault(finding["file"], []).append(finding)

    for file, file_findings in by_file.items():
        console.rule(f"[bold]{file}[/bold]")
        for finding in sorted(file_findings, key=lambda x: x["line"]):
            color = _SEVERITY_COLOR.get(finding["severity"], "white")
            console.print(
                f"[{color}]Line {finding['line']} — {finding['severity'].upper()} "
                f"— {finding['category']}[/{color}]"
            )
            console.print(f"  {finding['description']}")

            if finding.get("original_snippet"):
                console.print("  [dim]- Original:[/dim]")
                console.print(f"  [dim]{finding['original_snippet']}[/dim]")

            if finding.get("suggested_fix"):
                console.print("  [green]+ Suggested fix:[/green]")
                console.print(f"  [green]{finding['suggested_fix']}[/green]")

            if finding.get("explanation"):
                console.print(f"\n  [italic]{finding['explanation']}[/italic]")

            console.print()


def main():
    parser = argparse.ArgumentParser(description="LLM code review agent CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    review_parser = sub.add_parser("review", help="Review a file or directory")
    review_parser.add_argument("path", help="Path to a file or directory")
    review_parser.add_argument(
        "--provider",
        choices=PROVIDERS,
        help="Model provider to use (overrides MODEL_PROVIDER in .env)",
    )
    review_parser.add_argument(
        "--model",
        help="Specific model name to use (e.g. gpt-4o, deepseek-coder, llama-3.1-70b-versatile)",
    )

    args = parser.parse_args()
    if args.command == "review":
        review_command(args.path, args.provider, getattr(args, "model", None))


if __name__ == "__main__":
    main()