"""Centralized Anthropic API client with provider fallback and rate limit handling."""
import os
import re
import time
from datetime import datetime, timezone

import anthropic

# ---------------------------------------------------------------------------
# Provider setup
# ---------------------------------------------------------------------------

def _make_primary_client() -> anthropic.Anthropic | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    return anthropic.Anthropic(api_key=key)


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


def _seconds_until_any_reset() -> float:
    if not _rate_limits:
        return 300
    earliest = min(_rate_limits.values())
    return max(0, earliest - time.time())


def _get_providers() -> list[tuple[str, anthropic.Anthropic]]:
    providers = []
    primary = _make_primary_client()
    zai = _make_zai_client()
    if primary:
        providers.append(("primary", primary))
    if zai:
        providers.append(("zai", zai))
    if not providers:
        raise RuntimeError("No API keys configured (need ANTHROPIC_API_KEY or ZAI_API_KEY)")
    return providers


def _is_rate_limit_error(e: Exception) -> bool:
    """Check if an exception is a rate limit error."""
    if isinstance(e, anthropic.RateLimitError):
        return True
    text = str(e).lower()
    return any(s in text for s in ['429', 'rate limit', 'usage limit'])


def _is_auth_error(e: Exception) -> bool:
    """Check if an exception is an authentication error (try next provider)."""
    if isinstance(e, anthropic.AuthenticationError):
        return True
    text = str(e).lower()
    return any(s in text for s in ['401', 'authentication_error', 'invalid x-api-key', 'invalid api key'])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_message(**kwargs) -> anthropic.types.Message:
    """Create a message with automatic provider fallback and rate limit backoff."""
    providers = _get_providers()
    max_waits = 3

    for wait_round in range(max_waits + 1):
        for name, client in providers:
            if _is_rate_limited(name):
                continue
            try:
                return client.messages.create(**kwargs)
            except (anthropic.RateLimitError, anthropic.AuthenticationError, anthropic.APIStatusError) as e:
                if _is_rate_limit_error(e):
                    _mark_rate_limited(name, e)
                    continue
                if _is_auth_error(e):
                    print(f"[ScoreForge API] Provider '{name}' auth failed, trying next provider.", flush=True)
                    continue
                raise

        if wait_round < max_waits:
            wait_secs = _seconds_until_any_reset() + 5
            if wait_secs > 0:
                print(f"[ScoreForge API] All providers rate-limited. Waiting {wait_secs:.0f}s...", flush=True)
                time.sleep(wait_secs)

    raise RuntimeError("All API providers rate-limited after retries")


def stream_and_collect(**kwargs) -> str:
    """Stream a message and collect full text. Handles provider fallback.

    Returns the complete response text.
    """
    providers = _get_providers()
    max_waits = 3

    for wait_round in range(max_waits + 1):
        for name, client in providers:
            if _is_rate_limited(name):
                continue
            try:
                full_text = ""
                with client.messages.stream(**kwargs) as stream:
                    for text in stream.text_stream:
                        full_text += text
                return full_text
            except (anthropic.RateLimitError, anthropic.AuthenticationError, anthropic.APIStatusError) as e:
                if _is_rate_limit_error(e):
                    _mark_rate_limited(name, e)
                    continue
                if _is_auth_error(e):
                    print(f"[ScoreForge API] Provider '{name}' auth failed, trying next provider.", flush=True)
                    continue
                raise

        if wait_round < max_waits:
            wait_secs = _seconds_until_any_reset() + 5
            if wait_secs > 0:
                print(f"[ScoreForge API] All providers rate-limited. Waiting {wait_secs:.0f}s...", flush=True)
                time.sleep(wait_secs)

    raise RuntimeError("All API providers rate-limited after retries")
