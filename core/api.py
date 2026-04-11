"""Centralized API client with round-robin multi-provider rotation.

Supports:
  - Anthropic (Claude) via the Anthropic SDK
  - Ollama Cloud vision models via the Ollama HTTP API

Round-robin cycles through *all* healthy providers on successive calls so
every model gets used roughly equally.  Rate-limited or auth-failed
providers are temporarily skipped.
"""
import base64
import json
import os
import re
import time
import threading
from datetime import datetime, timezone
from typing import Optional

import anthropic
import httpx

# ---------------------------------------------------------------------------
# Round-robin state (thread-safe)
# ---------------------------------------------------------------------------
_rr_lock = threading.Lock()
_rr_index = 0  # next provider index

# Track the last model/provider used (set after every successful call)
_last_provider: Optional[str] = None
_last_model: Optional[str] = None

def get_last_model_info() -> dict:
    """Return info about the model used in the most recent API call."""
    return {"provider": _last_provider or "unknown", "model": _last_model or "unknown"}


# ---------------------------------------------------------------------------
# Provider setup
# ---------------------------------------------------------------------------

def _make_primary_client() -> anthropic.Anthropic | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    kwargs = {"api_key": key}
    if base_url:
        kwargs["base_url"] = base_url
    return anthropic.Anthropic(**kwargs)


def _make_zai_client() -> anthropic.Anthropic | None:
    key = os.environ.get("ZAI_API_KEY")
    url = os.environ.get("ZAI_BASE_URL")
    if not key or not url:
        return None
    return anthropic.Anthropic(api_key=key, base_url=url)


# In-memory rate limit state per provider
_rate_limits: dict[str, float] = {}  # provider_name -> unix timestamp when limit resets


def _parse_reset_time(error: Exception) -> float:
    """Extract reset timestamp from a rate limit error. Returns unix time."""
    text = str(error)
    m = re.search(r'reset[^"]*?(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2})', text, re.I)
    if m:
        try:
            dt = datetime.fromisoformat(m.group(1).replace(' ', 'T'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            pass
    return time.time() + 300


def _is_rate_limited(provider: str) -> bool:
    reset = _rate_limits.get(provider, 0)
    if time.time() < reset:
        return True
    if provider in _rate_limits:
        del _rate_limits[provider]
    return False


def _mark_rate_limited(provider: str, error: Exception) -> None:
    _rate_limits[provider] = _parse_reset_time(error)
    reset_str = datetime.fromtimestamp(_rate_limits[provider], tz=timezone.utc).strftime('%H:%M:%S UTC')
    print(f"[ScoreForge API] Provider '{provider}' rate-limited until {reset_str}", flush=True)


def _is_rate_limit_error(e: Exception) -> bool:
    if isinstance(e, anthropic.RateLimitError):
        return True
    text = str(e).lower()
    return any(s in text for s in ['429', 'rate limit', 'usage limit'])


def _is_auth_error(e: Exception) -> bool:
    if isinstance(e, anthropic.AuthenticationError):
        return True
    text = str(e).lower()
    return any(s in text for s in ['401', 'authentication_error', 'invalid x-api-key', 'invalid api key'])


# ---------------------------------------------------------------------------
# Provider registry — unified list of all providers
# ---------------------------------------------------------------------------

class Provider:
    """Abstraction over an Anthropic SDK client or an Ollama Cloud endpoint."""

    def __init__(self, name: str, kind: str, model: str,
                 anthropic_client: anthropic.Anthropic | None = None,
                 ollama_base_url: str | None = None,
                 ollama_api_key: str | None = None):
        self.name = name
        self.kind = kind  # "anthropic" or "ollama"
        self.model = model
        self.anthropic_client = anthropic_client
        self.ollama_base_url = ollama_base_url
        self.ollama_api_key = ollama_api_key


# Ollama Cloud vision models to round-robin
OLLAMA_VISION_MODELS = [
    "qwen3-vl:235b-instruct",
    "gemma4:31b",
    "kimi-k2.5",
]

# Default Anthropic model for vision
ANTHROPIC_VISION_MODEL = "claude-opus-4-20250514"


def _build_provider_list() -> list[Provider]:
    """Build the full provider list for round-robin rotation."""
    providers: list[Provider] = []

    # Anthropic primary
    primary = _make_primary_client()
    if primary:
        providers.append(Provider(
            name="anthropic",
            kind="anthropic",
            model=ANTHROPIC_VISION_MODEL,
            anthropic_client=primary,
        ))

    # Z.AI — removed from vision rotation (glm-5.1 is text-only, no vision support)
    # Will re-add when Z.AI offers a vision-capable model

    # Ollama Cloud vision models
    ollama_key = os.environ.get("OLLAMA_CLOUD_API_KEY")
    ollama_url = os.environ.get("OLLAMA_CLOUD_URL", "https://api.ollama.com")
    if ollama_key:
        for model_name in OLLAMA_VISION_MODELS:
            providers.append(Provider(
                name=f"ollama:{model_name}",
                kind="ollama",
                model=model_name,
                ollama_base_url=ollama_url,
                ollama_api_key=ollama_key,
            ))

    if not providers:
        raise RuntimeError("No API keys configured (need ANTHROPIC_API_KEY or OLLAMA_CLOUD_API_KEY)")

    return providers


def _get_all_providers() -> list[Provider]:
    """Return cached provider list (rebuilt each call to pick up env changes)."""
    return _build_provider_list()


def get_provider_roster() -> list[dict]:
    """Return list of all configured providers for UI display."""
    providers = _get_all_providers()
    return [
        {"name": p.name, "kind": p.kind, "model": p.model, "rateLimited": _is_rate_limited(p.name)}
        for p in providers
    ]


# ---------------------------------------------------------------------------
# Ollama Cloud API call
# ---------------------------------------------------------------------------

def _extract_images_from_anthropic_messages(messages: list[dict]) -> tuple[str, list[str]]:
    """Extract text prompt and base64 images from Anthropic-format messages.

    Returns (text_prompt, [base64_image_strings]).
    """
    text_parts = []
    images = []

    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block["text"])
                    elif block.get("type") == "image":
                        src = block.get("source", {})
                        if src.get("type") == "base64":
                            images.append(src["data"])

    return "\n".join(text_parts), images


def _call_ollama(provider: Provider, messages: list[dict], max_tokens: int = 16000,
                 **_ignored) -> str:
    """Call Ollama Cloud API and return response text."""
    text_prompt, images = _extract_images_from_anthropic_messages(messages)

    ollama_messages = [{
        "role": "user",
        "content": text_prompt,
    }]
    if images:
        ollama_messages[0]["images"] = images

    payload = {
        "model": provider.model,
        "messages": ollama_messages,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
        },
    }

    headers = {
        "Authorization": f"Bearer {provider.ollama_api_key}",
        "Content-Type": "application/json",
    }

    url = f"{provider.ollama_base_url.rstrip('/')}/api/chat"

    # Ollama vision calls can be slow — generous timeout
    with httpx.Client(timeout=300) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    return data.get("message", {}).get("content", "")


# ---------------------------------------------------------------------------
# Anthropic API call
# ---------------------------------------------------------------------------

def _call_anthropic(provider: Provider, **kwargs) -> str:
    """Call Anthropic API via SDK and return response text (streaming)."""
    # Override model to the provider's model
    kwargs["model"] = provider.model
    client = provider.anthropic_client

    full_text = ""
    with client.messages.stream(**kwargs) as stream:
        for text in stream.text_stream:
            full_text += text
    return full_text


# ---------------------------------------------------------------------------
# Public API — round-robin with fallback
# ---------------------------------------------------------------------------

def stream_and_collect(**kwargs) -> str:
    """Make a vision API call with round-robin provider rotation.

    Accepts Anthropic-format kwargs (model, max_tokens, messages, etc.).
    Automatically translates for Ollama providers.

    Returns the complete response text.  Sets _last_provider / _last_model
    for the caller to retrieve via get_last_model_info().
    """
    global _rr_index, _last_provider, _last_model

    providers = _get_all_providers()
    n = len(providers)
    max_waits = 2

    for wait_round in range(max_waits + 1):
        # Pick starting index via round-robin
        with _rr_lock:
            start = _rr_index % n
            _rr_index += 1

        # Try each provider starting from the round-robin position
        for offset in range(n):
            idx = (start + offset) % n
            p = providers[idx]

            if _is_rate_limited(p.name):
                continue

            try:
                print(f"[ScoreForge API] Using provider '{p.name}' (model: {p.model})", flush=True)

                if p.kind == "anthropic":
                    result = _call_anthropic(p, **kwargs)
                else:
                    result = _call_ollama(
                        p,
                        messages=kwargs.get("messages", []),
                        max_tokens=kwargs.get("max_tokens", 16000),
                    )

                _last_provider = p.name
                _last_model = p.model
                print(f"[ScoreForge API] Success from '{p.name}'", flush=True)
                return result

            except Exception as e:
                if _is_rate_limit_error(e):
                    _mark_rate_limited(p.name, e)
                    continue
                if _is_auth_error(e):
                    print(f"[ScoreForge API] Provider '{p.name}' auth failed, trying next.", flush=True)
                    continue
                # For Ollama HTTP errors, try next provider
                if isinstance(e, httpx.HTTPStatusError):
                    print(f"[ScoreForge API] Provider '{p.name}' HTTP error: {e}", flush=True)
                    continue
                if isinstance(e, (httpx.ConnectError, httpx.TimeoutException)):
                    print(f"[ScoreForge API] Provider '{p.name}' connection error: {e}", flush=True)
                    continue
                # Unknown error — log and try next
                print(f"[ScoreForge API] Provider '{p.name}' error: {e}", flush=True)
                continue

        # All providers failed this round
        if wait_round < max_waits:
            wait_secs = 30
            print(f"[ScoreForge API] All providers failed. Waiting {wait_secs}s before retry...", flush=True)
            time.sleep(wait_secs)

    raise RuntimeError("All API providers failed after retries")


def create_message(**kwargs) -> anthropic.types.Message:
    """Create a message using the primary Anthropic client (non-round-robin).

    This is kept for backward compatibility with non-vision calls.
    For vision extraction, use stream_and_collect() instead.
    """
    primary = _make_primary_client()
    if not primary:
        raise RuntimeError("No ANTHROPIC_API_KEY configured for create_message()")
    return primary.messages.create(**kwargs)
