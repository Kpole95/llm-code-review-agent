"""Wrapper around the Anthropic Messages API: chat(), chat_json(), chat_tool()."""
import json

import anthropic
from langsmith.wrappers import wrap_anthropic

from src.config import settings

if not settings.anthropic_api_key:
    raise RuntimeError(
        "ANTHROPIC_API_KEY not set. Did you create .env from .env.example?"
    )

_client = wrap_anthropic(anthropic.Anthropic(api_key=settings.anthropic_api_key))


def chat(
    prompt: str,
    system: str | None = None,
    max_tokens: int = 1024,
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> str:
    """Send a single user message to Claude and return the text reply."""
    kwargs = {
        "model": settings.anthropic_model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    extra = {}
    if tags:
        extra["tags"] = tags
    if metadata:
        extra["metadata"] = metadata
    if extra:
        kwargs["langsmith_extra"] = extra

    resp = _client.messages.create(**kwargs)
    return "".join(block.text for block in resp.content if block.type == "text")


def chat_json(
    prompt: str,
    system: str | None = None,
    max_tokens: int = 1024,
    tags: list[str] | None = None,
    metadata: dict | None = None,
):
    """Like chat(), but parses the reply as JSON, with a one-shot repair retry."""
    raw = chat(
        prompt, system=system, max_tokens=max_tokens, tags=tags, metadata=metadata
    ).strip()
    cleaned = _strip_fences(raw)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        repair_prompt = (
            "The following text was supposed to be valid JSON but failed to "
            f"parse with error: {e}\n\n"
            "Fix the JSON syntax and return ONLY the corrected JSON, no prose, "
            f"no markdown fences:\n\n{cleaned}"
        )
        repaired = chat(
            repair_prompt,
            max_tokens=max_tokens,
            tags=(tags or []) + ["json_repair"],
            metadata=metadata,
        ).strip()
        return json.loads(_strip_fences(repaired))


def chat_tool(
    prompt: str,
    tool: dict,
    system: str | None = None,
    max_tokens: int = 2048,
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> dict:
    """Call Claude with a forced tool call so the response matches a fixed schema."""
    kwargs = {
        "model": settings.anthropic_model,
        "max_tokens": max_tokens,
        "tools": [tool],
        "tool_choice": {"type": "tool", "name": tool["name"]},
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    extra = {}
    if tags:
        extra["tags"] = tags
    if metadata:
        extra["metadata"] = metadata
    if extra:
        kwargs["langsmith_extra"] = extra

    resp = _client.messages.create(**kwargs)

    for block in resp.content:
        if block.type == "tool_use":
            return block.input

    raise RuntimeError(
        f"chat_tool: no tool_use block in response. Content: {[b.type for b in resp.content]}"
    )


def _strip_fences(text: str) -> str:
    """Remove a wrapping markdown code fence if present."""
    if text.startswith("```"):
        text = text.split("```")[1]
        lines = text.split("\n", 1)
        if len(lines) > 1 and lines[0].strip().isalpha():
            text = lines[1]
    return text.strip()
