"""Loads changed files from a public GitHub PR via the REST API."""
import os
import re
import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.parsing.pr_loader import EXT_LANG

# Suppress the warning that Python throws when we bypass SSL verification
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_PR_URL_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")

def get_vpn_proof_session():
    """Creates an HTTP session built to survive corporate VPNs."""
    session = requests.Session()
    
    # Retry up to 3 times, waiting a few seconds between attempts
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # FOR VPN USERS: Force the session to ignore VPN SSL inspection
    session.verify = False 
    
    return session


def load_pr_files(pr_url: str) -> list[dict]:
    """Given a GitHub PR URL, return list[FileInput] for every changed supported file."""
    match = _PR_URL_RE.search(pr_url)
    if not match:
        raise ValueError(
            "Invalid GitHub PR URL — expected format: https://github.com/owner/repo/pull/123"
        )

    owner, repo, number = match.groups()
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}/files"
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "LLM-Code-Review-Agent-v1" 
    }
    
    token = os.getenv('GITHUB_ACCESS_TOKEN')
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # Use our new VPN-proof session instead of standard requests.get
    session = get_vpn_proof_session()

    resp = session.get(api_url, headers=headers, timeout=15)
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

        # Fetch the raw code using the VPN-proof session
        content_resp = session.get(raw_url, headers=headers, timeout=15)
        content_resp.raise_for_status()

        files.append({
            "path": filename,
            "content": content_resp.text,
            "language": EXT_LANG[ext],
        })

    return files