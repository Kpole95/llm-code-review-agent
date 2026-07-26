"""
LLM client — supports Anthropic, OpenAI, DeepSeek, Groq, Gemini, and Ollama.
Switch providers with MODEL_PROVIDER in .env or via --provider in the CLI.
Public interface: chat(), chat_json(), chat_tool() — identical across all backends.
"""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class _Backend(ABC):
    @abstractmethod
    def chat(self, prompt, system, max_tokens, tags, metadata) -> str: ...

    @abstractmethod
    def chat_tool(self, prompt, tool, system, max_tokens, tags, metadata) -> dict: ...


# ── Anthropic ─────────────────────────────────────────────────────────────────

class _AnthropicBackend(_Backend):
    def __init__(self):
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set.")
        import anthropic
        from langsmith.wrappers import wrap_anthropic
        self._client = wrap_anthropic(
            anthropic.Anthropic(api_key=settings.anthropic_api_key)
        )

    def chat(self, prompt, system=None, max_tokens=1024, tags=None, metadata=None) -> str:
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
        resp = self._client.messages.create(**kwargs)
        return "".join(b.text for b in resp.content if b.type == "text")

    def chat_tool(self, prompt, tool, system=None, max_tokens=2048, tags=None, metadata=None) -> dict:
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
        resp = self._client.messages.create(**kwargs)
        for block in resp.content:
            if block.type == "tool_use":
                return block.input
        raise RuntimeError(f"No tool_use block. Content: {[b.type for b in resp.content]}")


# ── OpenAI-compatible (OpenAI, DeepSeek, Groq) ───────────────────────────────

class _OpenAICompatibleBackend(_Backend):
    """
    Covers OpenAI, DeepSeek, and Groq — all use the OpenAI API format.
    All three support native function calling so chat_tool is reliable.

    Groq model IDs:
      openai/gpt-oss-120b    — best quality, 500 t/s
      openai/gpt-oss-20b     — fastest, cheapest, 1000 t/s
      llama-3.3-70b-versatile — strong general model
      llama-3.1-8b-instant   — ultra fast free tier
      qwen/qwen3.6-27b       — Alibaba, vision capable

    DeepSeek model IDs:
      deepseek-coder          — best for code
      deepseek-chat           — general purpose
    """
    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        if not api_key:
            raise RuntimeError(
                f"API key not set for MODEL_PROVIDER={settings.model_provider}. "
                f"Check your .env file."
            )
        from openai import OpenAI
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self._model = model

    def _messages(self, prompt, system):
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        return msgs

    def chat(self, prompt, system=None, max_tokens=1024, tags=None, metadata=None) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=self._messages(prompt, system),
        )
        return resp.choices[0].message.content or ""

    def chat_tool(self, prompt, tool, system=None, max_tokens=2048, tags=None, metadata=None) -> dict:
        # Convert Anthropic tool schema → OpenAI function schema
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool["input_schema"],
            },
        }
        resp = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=self._messages(prompt, system),
            tools=[openai_tool],
            tool_choice={"type": "function", "function": {"name": tool["name"]}},
        )
        tool_calls = resp.choices[0].message.tool_calls
        if tool_calls:
            return json.loads(tool_calls[0].function.arguments)
        raise RuntimeError(f"No tool_call in response from {self._model}")


# ── Google Gemini ─────────────────────────────────────────────────────────────

class _GeminiBackend(_Backend):
    """
    Google Gemini via google-generativeai SDK.
    Uses example-driven JSON prompting for chat_tool — simpler and more
    reliable than mapping Gemini's function calling to Anthropic's schema format.

    Model IDs: gemini-2.0-flash, gemini-1.5-pro, gemini-1.5-flash
    """
    def __init__(self):
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY not set.")
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        self._genai = genai
        self._model_name = settings.gemini_model

    def _model(self, system=None):
        kwargs: dict = {"model_name": self._model_name}
        if system:
            kwargs["system_instruction"] = system
        return self._genai.GenerativeModel(**kwargs)

    def chat(self, prompt, system=None, max_tokens=1024, tags=None, metadata=None) -> str:
        resp = self._model(system).generate_content(
            prompt,
            generation_config={"max_output_tokens": max_tokens},
        )
        return resp.text

    def chat_tool(self, prompt, tool, system=None, max_tokens=2048, tags=None, metadata=None) -> dict:
        props = tool["input_schema"].get("properties", {})
        findings_key, example_item = _build_example(props)
        json_prompt = _json_prompt(prompt, findings_key, example_item)
        resp = self._model(system).generate_content(
            json_prompt,
            generation_config={"max_output_tokens": max_tokens},
        )
        return _extract_json(resp.text)


# ── Ollama (local / self-hosted) ──────────────────────────────────────────────

class _OllamaBackend(_Backend):
    """
    Calls a local Ollama instance or any self-hosted OpenAI-compatible server.
    Uses example-driven JSON prompting — local models don't support function
    calling reliably. GPU strongly recommended; CPU is 2-8 min/file.

    Good local models: glm4:latest, qwen2.5-coder:7b, llama3.1:8b
    """
    def __init__(self):
        self._base = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model
        self._http = httpx.Client(timeout=600.0)

    def _post(self, messages, max_tokens):
        resp = self._http.post(
            f"{self._base}/api/chat",
            json={"model": self._model, "messages": messages,
                  "stream": False, "options": {"num_predict": max_tokens}},
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def chat(self, prompt, system=None, max_tokens=1024, tags=None, metadata=None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._post(messages, max_tokens)

    def chat_tool(self, prompt, tool, system=None, max_tokens=2048, tags=None, metadata=None) -> dict:
        props = tool["input_schema"].get("properties", {})
        findings_key, example_item = _build_example(props)
        json_prompt = _json_prompt(prompt, findings_key, example_item)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": json_prompt})
        return _extract_json(self._post(messages, max_tokens))


# ── Shared helpers ────────────────────────────────────────────────────────────

def _build_example(props: dict) -> tuple[str, dict]:
    """Build a concrete example item from the tool's array property schema."""
    findings_key = "findings"
    example_item: dict = {}
    for key, val in props.items():
        if val.get("type") == "array" and "items" in val:
            findings_key = key
            for field, fval in val["items"].get("properties", {}).items():
                if "enum" in fval:
                    example_item[field] = fval["enum"][0]
                elif fval.get("type") == "integer":
                    example_item[field] = 1
                else:
                    example_item[field] = f"example {field}"
            break
    return findings_key, example_item


def _json_prompt(prompt: str, findings_key: str, example_item: dict) -> str:
    example = json.dumps({findings_key: [example_item]}, indent=2)
    empty   = json.dumps({findings_key: []}, indent=2)
    return (
        f"{prompt}\n\n"
        f"Return a JSON object with your findings. Example format:\n{example}\n\n"
        f"If there are no issues, return:\n{empty}\n\n"
        f"Return ONLY the JSON — no explanation, no markdown, no extra text."
    )


def _extract_json(text: str) -> dict:
    """Extract a JSON object from model output that may contain surrounding text."""
    try:
        return json.loads(_strip_fences(text))
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start != -1:
        try:
            return json.loads(text[start:])
        except json.JSONDecodeError:
            pass
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    logger.warning("Could not extract JSON from response. Returning empty findings.")
    logger.debug("Raw response: %s", text[:500])
    return {"findings": []}


# ── Factory ───────────────────────────────────────────────────────────────────

def _build_backend() -> _Backend:
    p = settings.model_provider.lower()
    if p == "anthropic":
        return _AnthropicBackend()
    if p == "openai":
        return _OpenAICompatibleBackend(
            settings.openai_api_key, settings.openai_model
        )
    if p == "deepseek":
        return _OpenAICompatibleBackend(
            settings.deepseek_api_key, settings.deepseek_model,
            base_url="https://api.deepseek.com/v1",
        )
    if p == "groq":
        return _OpenAICompatibleBackend(
            settings.groq_api_key, settings.groq_model,
            base_url="https://api.groq.com/openai/v1",
        )
    if p == "gemini":
        return _GeminiBackend()
    if p == "ollama":
        return _OllamaBackend()
    raise ValueError(
        f"Unknown MODEL_PROVIDER '{p}'. "
        "Choose: anthropic | openai | deepseek | groq | gemini | ollama"
    )


_backend = _build_backend()


# ── Public interface ──────────────────────────────────────────────────────────

def chat(prompt, system=None, max_tokens=1024, tags=None, metadata=None) -> str:
    return _backend.chat(prompt, system=system, max_tokens=max_tokens,
                         tags=tags, metadata=metadata)


def chat_json(prompt, system=None, max_tokens=1024, tags=None, metadata=None):
    raw = chat(prompt, system=system, max_tokens=max_tokens,
               tags=tags, metadata=metadata).strip()
    cleaned = _strip_fences(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        repair = (f"This JSON failed to parse: {e}\n\n"
                  f"Return ONLY corrected JSON, no prose, no fences:\n\n{cleaned}")
        repaired = chat(repair, max_tokens=max_tokens,
                        tags=(tags or []) + ["json_repair"],
                        metadata=metadata).strip()
        return json.loads(_strip_fences(repaired))


def chat_tool(prompt, tool, system=None, max_tokens=2048, tags=None, metadata=None) -> dict:
    return _backend.chat_tool(prompt, tool, system=system, max_tokens=max_tokens,
                              tags=tags, metadata=metadata)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        lines = text.split("\n", 1)
        if len(lines) > 1 and lines[0].strip().isalpha():
            text = lines[1]
    return text.strip()