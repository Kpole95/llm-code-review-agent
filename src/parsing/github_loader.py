"""Loads changed files from a public GitHub PR via the REST API."""
import os
import re
import requests

from src.parsing.pr_loader import EXT_LANG

_PR_URL_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")

def load_pr_files(pr_url: str) -> list[dict]:
    """Given a GitHub PR URL, return list[FileInput] for every changed supported file."""
    match = _PR_URL_RE.search(pr_url)
    if not match:
        raise ValueError(
            "Invalid GitHub PR URL — expected format: https://github.com/owner/repo/pull/123"
        )

    owner, repo, number = match.groups()
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}/files"
    
    # 1. Add the User-Agent to prevent the SSL EOF drop
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "LLM-Code-Review-Agent-v1" 
    }
    
    # 2. Safely apply the token ONLY if it exists in the environment
    # Note: GitHub recently prefers "Bearer" over "token", though both usually work.
    token = os.getenv('GITHUB_ACCESS_TOKEN')
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = requests.get(api_url, headers=headers, timeout=15)
    resp.raise_for_status()

    files = []
    for item in resp.json():
        filename = item["filename"]
        ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""

        if ext not in EXT_LANG:
            continue

        raw_url = item.get("raw_url")
        if not raw_url:
            continue

        # This request will now succeed because the User-Agent is in the headers
        content_resp = requests.get(raw_url, headers=headers, timeout=15)
        content_resp.raise_for_status()

        files.append({
            "path": filename,
            "content": content_resp.text,
            "language": EXT_LANG[ext],
        })

    return files