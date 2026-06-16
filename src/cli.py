"""Command-line entry point. Usage: uv run python -m src.cli review <path>"""
import argparse

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


def review_command(path: str):
    """Load a file or directory, run the pipeline, print results grouped by file."""
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
    review_parser.add_argument("path", help="Path to a file or directory to review")

    args = parser.parse_args()
    if args.command == "review":
        review_command(args.path)


if __name__ == "__main__":
    main()
