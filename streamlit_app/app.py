"""Streamlit front-end. Calls the API over HTTP rather than importing run_review() directly."""
import html
import os
import sys

import httpx
import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.parsing.github_loader import load_pr_files  # noqa: E402
from src.parsing.pr_loader import EXT_LANG  # noqa: E402

API_URL = os.getenv("API_URL", "http://localhost:8000")

SUPPORTED_LANGUAGES = sorted(set(EXT_LANG.values()))

_LANG_DISPLAY = {
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "java": "Java",
    "go": "Go",
}
_LANG_TO_EXT = {
    "python": "py",
    "javascript": "js",
    "typescript": "ts",
    "java": "java",
    "go": "go",
}

_SEVERITY_STYLE = {
    "critical": {"color": "#F0506E", "label": "CRITICAL"},
    "high": {"color": "#F2994A", "label": "HIGH"},
    "medium": {"color": "#E8C547", "label": "MEDIUM"},
    "low": {"color": "#7C8B9C", "label": "LOW"},
}
_SEVERITY_ORDER = ["critical", "high", "medium", "low"]

st.set_page_config(page_title="LLM Code Review Agent", page_icon="🔍", layout="wide")

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"]  { font-family: 'Inter', sans-serif; }
.stApp { background-color: #0E1116; color: #ECEFF4; }
h1, h2, h3 { font-family: 'Space Grotesk', sans-serif !important; letter-spacing: -0.01em; }
#MainMenu, footer, header { visibility: hidden; }

.hero-title { font-family: 'Space Grotesk', sans-serif; font-size: 2.05rem; font-weight: 700; margin-bottom: 0.1rem; }
.hero-sub { color: #8D95A3; font-size: 0.95rem; margin-bottom: 1.6rem; }

.finding-card {
    background: #151922;
    border: 1px solid #262B36;
    border-left: 4px solid var(--sev-color, #7C8B9C);
    border-radius: 8px;
    padding: 1rem 1.2rem;
    margin-bottom: 1rem;
}
.finding-header { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.4rem; flex-wrap: wrap; }
.severity-badge {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.04em;
    padding: 0.15rem 0.5rem; border-radius: 4px; color: #0E1116;
}
.finding-location { color: #8D95A3; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; }
.finding-category { color: #ECEFF4; font-weight: 600; font-size: 0.95rem; }
.finding-desc { color: #C2C8D2; font-size: 0.92rem; margin: 0.5rem 0 0.8rem; line-height: 1.5; }

.code-block {
    font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;
    padding: 0.6rem 0.8rem; border-radius: 6px;
    white-space: pre-wrap; word-break: break-word;
    margin-bottom: 0.5rem; line-height: 1.5;
}
.code-original { background: rgba(240, 80, 110, 0.08); border: 1px solid rgba(240, 80, 110, 0.25); color: #F0A8B5; }
.code-fix { background: rgba(79, 209, 165, 0.08); border: 1px solid rgba(79, 209, 165, 0.25); color: #9FE3C8; }
.code-label { font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #8D95A3; margin-bottom: 0.25rem; }

.explanation { font-size: 0.88rem; color: #B8C4D9; font-style: italic; border-top: 1px solid #262B36; padding-top: 0.6rem; margin-top: 0.6rem; }

.clean-banner, .empty-banner {
    border-radius: 8px; padding: 0.9rem 1.1rem;
    font-family: 'JetBrains Mono', monospace; font-size: 0.9rem;
}
.clean-banner { background: rgba(79, 209, 165, 0.08); border: 1px solid rgba(79, 209, 165, 0.3); color: #4FD1A5; }
.empty-banner { background: #151922; border: 1px solid #262B36; color: #8D95A3; }

.file-rule { font-family: 'JetBrains Mono', monospace; color: #8D95A3; font-size: 0.85rem; margin: 1.4rem 0 0.6rem; border-bottom: 1px solid #262B36; padding-bottom: 0.4rem; }

.stButton button {
    background-color: #6C8EF5; color: #0E1116; font-weight: 600;
    border-radius: 6px; border: none; padding: 0.5rem 1.4rem;
}
.stButton button:hover { background-color: #87A1F7; color: #0E1116; }
section[data-testid="stSidebar"] { background-color: #0B0E14; border-right: 1px solid #262B36; }
</style>
""",
    unsafe_allow_html=True,
)

st.markdown('<div class="hero-title">🔍 LLM Code Review Agent</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="hero-sub">Finds bugs and security issues across Python, '
    "JavaScript, TypeScript, Java, and Go — grounded in OWASP guidance, "
    "with suggested fixes and plain-English explanations.</div>",
    unsafe_allow_html=True,
)

if "findings" not in st.session_state:
    st.session_state.findings = None

with st.sidebar:
    st.markdown("#### Review input")
    mode = st.radio("Source", ["Paste code", "GitHub PR"], label_visibility="collapsed")

    language = None
    if mode == "Paste code":
        language = st.selectbox(
            "Language",
            SUPPORTED_LANGUAGES,
            format_func=lambda l: _LANG_DISPLAY.get(l, l.title()),
        )

    st.markdown("---")
    st.markdown(
        f"<span style='color:#8D95A3; font-size:0.78rem;'>API target<br>"
        f"<code style='color:#9FB3D9;'>{html.escape(API_URL)}</code></span>",
        unsafe_allow_html=True,
    )

code, pr_url = None, None
if mode == "Paste code":
    code = st.text_area(
        "Code",
        height=320,
        placeholder=f"Paste your {_LANG_DISPLAY.get(language, language)} code here...",
        label_visibility="collapsed",
    )
else:
    pr_url = st.text_input(
        "GitHub PR URL",
        placeholder="https://github.com/owner/repo/pull/123",
        label_visibility="collapsed",
    )

run = st.button("Run review", type="primary")

if run:
    if mode == "Paste code":
        if not code or not code.strip():
            st.warning("Paste some code first.")
            st.stop()
        ext = _LANG_TO_EXT.get(language, "txt")
        files_payload = [
            {"path": f"pasted_snippet.{ext}", "content": code, "language": language}
        ]
    else:
        if not pr_url or not pr_url.strip():
            st.warning("Enter a GitHub PR URL first.")
            st.stop()
        with st.spinner("$ fetching pull request files..."):
            try:
                files_payload = load_pr_files(pr_url)
            except Exception as e:
                st.error(f"Could not load PR: {e}")
                st.stop()
        if not files_payload:
            st.warning("No supported files found in this PR.")
            st.stop()

    with st.spinner("$ analyzing code — this can take a minute..."):
        try:
            response = httpx.post(
                f"{API_URL}/review", json={"files": files_payload}, timeout=300
            )
            response.raise_for_status()
            st.session_state.findings = response.json()["findings"]
        except Exception as e:
            st.error(f"Review failed: {e}")
            st.stop()

findings = st.session_state.findings

if findings is None:
    st.markdown(
        '<div class="empty-banner">$ waiting for input — paste code or a '
        "GitHub PR URL, then run a review.</div>",
        unsafe_allow_html=True,
    )
elif not findings:
    st.markdown(
        '<div class="clean-banner">$ no issues found — code looks clean.</div>',
        unsafe_allow_html=True,
    )
else:
    counts = {}
    for f in findings:
        sev = f.get("severity", "low")
        counts[sev] = counts.get(sev, 0) + 1
    summary_html = " &nbsp; ".join(
        f"<span class='severity-badge' style='background:{_SEVERITY_STYLE[s]['color']}'>"
        f"{counts[s]} {s.upper()}</span>"
        for s in _SEVERITY_ORDER
        if counts.get(s)
    )
    st.markdown(f"<div style='margin-bottom:1rem;'>{summary_html}</div>", unsafe_allow_html=True)

    by_file: dict[str, list[dict]] = {}
    for f in findings:
        by_file.setdefault(f["file"], []).append(f)

    for file, file_findings in by_file.items():
        st.markdown(f'<div class="file-rule">{html.escape(file)}</div>', unsafe_allow_html=True)
        for f in sorted(file_findings, key=lambda x: x["line"]):
            sev = f.get("severity", "low")
            style = _SEVERITY_STYLE.get(sev, _SEVERITY_STYLE["low"])
            category_label = html.escape(f["category"].replace("_", " ").title())

            card = (
                f'<div class="finding-card" style="--sev-color:{style["color"]}">'
                f'<div class="finding-header">'
                f'<span class="severity-badge" style="background:{style["color"]}">{style["label"]}</span>'
                f'<span class="finding-location">Line {f["line"]}</span>'
                f'<span class="finding-category">{category_label}</span>'
                f"</div>"
                f'<div class="finding-desc">{html.escape(f["description"])}</div>'
            )
            if f.get("original_snippet"):
                card += (
                    '<div class="code-label">ORIGINAL</div>'
                    f'<div class="code-block code-original">{html.escape(f["original_snippet"])}</div>'
                )
            if f.get("suggested_fix"):
                card += (
                    '<div class="code-label">SUGGESTED FIX</div>'
                    f'<div class="code-block code-fix">{html.escape(f["suggested_fix"])}</div>'
                )
            if f.get("explanation"):
                card += f'<div class="explanation">{html.escape(f["explanation"])}</div>'
            card += "</div>"

            st.markdown(card, unsafe_allow_html=True)
