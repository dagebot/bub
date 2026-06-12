#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
# ]
# ///

"""
Single-shot Chat Completions helper for Xiaomi's free MiMo Auto API.

This is an unofficial wrapper around an endpoint extracted from MiMo Code
(see ../references/api.md for the schema). Use it as a manual fallback when
Bub's normal LLM provider is unavailable — not as a wired-in replacement.

Usage:
    uv run mimo_chat.py "Your prompt here"
    echo "Long prompt" | uv run mimo_chat.py --system "You are a ..."
    uv run mimo_chat.py --json "Prompt"   # print full OpenAI response
    uv run mimo_chat.py --stream "Prompt" # print SSE chunks as they arrive
    uv run mimo_chat.py --no-cache "Prompt"   # force fresh JWT
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_BASE_URL = "https://api.xiaomimimo.com"
DEFAULT_CACHE = "/tmp/bub-mimo-jwt"
DEFAULT_CLIENT = "bub-agent"
DEFAULT_MODEL = "mimo-auto"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.7
REQUEST_TIMEOUT = 30


def cache_path() -> Path:
    p = Path(os.environ.get("BUB_MIMO_CACHE", DEFAULT_CACHE))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def read_cached_jwt() -> str | None:
    p = cache_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    jwt = data.get("jwt")
    exp = data.get("exp", 0)
    # exp is milliseconds; give a 30 s cushion
    if jwt and exp * 1000 > (time.time() + 30) * 1000:
        return jwt
    return None


def write_cached_jwt(jwt: str, exp_ms: int) -> None:
    p = cache_path()
    p.write_text(json.dumps({"jwt": jwt, "exp": exp_ms}), encoding="utf-8")
    try:
        p.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def bootstrap_jwt(base_url: str, client: str) -> str:
    url = f"{base_url}/api/free-ai/bootstrap"
    resp = requests.post(
        url,
        json={"client": client},
        headers={"Content-Type": "application/json"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    jwt = data.get("jwt")
    exp = data.get("exp", 0)
    if not jwt:
        raise RuntimeError(f"bootstrap response missing 'jwt': {data!r}")
    write_cached_jwt(jwt, exp)
    return jwt


def get_jwt(base_url: str, client: str, *, force: bool = False) -> str:
    if not force:
        cached = read_cached_jwt()
        if cached:
            return cached
    return bootstrap_jwt(base_url, client)


def chat(
    base_url: str,
    client: str,
    messages: list[dict[str, str]],
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    stream: bool = False,
    force_jwt: bool = False,
) -> dict[str, Any] | requests.Response:
    jwt = get_jwt(base_url, client, force=force_jwt)
    url = f"{base_url}/api/free-ai/openai/chat"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {jwt}",
        "X-Mimo-Source": "mimocode-cli-free",
    }
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
    }
    resp = requests.post(
        url, json=body, headers=headers, timeout=REQUEST_TIMEOUT, stream=stream
    )
    if resp.status_code == 401 and not force_jwt:
        # JWT likely expired between cache read and use; refresh once
        get_jwt(base_url, client, force=True)
        resp = requests.post(
            url, json=body, headers=headers, timeout=REQUEST_TIMEOUT, stream=stream
        )
    return resp


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt and args.prompt != "-":
        return args.prompt
    data = sys.stdin.read()
    if not data.strip():
        print("error: no prompt provided (use --prompt or stdin)", file=sys.stderr)
        sys.exit(2)
    return data


def render_text(resp: dict[str, Any]) -> str:
    try:
        msg = resp["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return ""
    parts: list[str] = []
    rc = msg.get("reasoning_content")
    content = msg.get("content")
    if rc:
        parts.append(f"<think>\n{rc}\n</think>\n")
    if content:
        parts.append(content)
    return "\n".join(parts).strip()


def render_stream(resp: requests.Response) -> str:
    """Best-effort SSE renderer. Returns the final assistant text."""
    pieces: list[str] = []
    final_text = ""
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw:
            continue
        if raw.startswith("data:"):
            data = raw[len("data:"):].strip()
        else:
            data = raw.strip()
        if not data or data == "[DONE]":
            continue
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        delta = chunk.get("choices", [{}])[0].get("delta") or {}
        if delta.get("content"):
            pieces.append(delta["content"])
        # Some servers flush the full message in the final chunk instead of a delta
        msg = chunk.get("choices", [{}])[0].get("message")
        if msg and msg.get("content"):
            final_text = msg["content"]
    return (final_text or "".join(pieces)).strip()


def main() -> int:
    p = argparse.ArgumentParser(
        description="Single-shot MiMo Auto Chat Completions (unofficial, free).",
    )
    p.add_argument(
        "prompt", nargs="?", default=None,
        help='Prompt to send. Use "-" to read from stdin (default).',
    )
    p.add_argument("--system", "-s", default=None, help="Optional system message.")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    p.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    p.add_argument("--stream", action="store_true", help="Receive SSE chunks.")
    p.add_argument("--json", action="store_true", help="Print full OpenAI response as JSON.")
    p.add_argument("--no-cache", action="store_true", help="Force a fresh JWT.")
    args = p.parse_args()

    base_url = os.environ.get("BUB_MIMO_BASE_URL", DEFAULT_BASE_URL)
    client = os.environ.get("BUB_MIMO_CLIENT", DEFAULT_CLIENT)

    user_prompt = read_prompt(args)
    messages: list[dict[str, str]] = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": user_prompt})

    resp = chat(
        base_url,
        client,
        messages,
        model=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        stream=args.stream,
        force_jwt=args.no_cache,
    )

    if args.stream:
        if isinstance(resp, requests.Response) and resp.status_code == 200:
            text = render_stream(resp)
            print(text)
            return 0
        # fall through to error handling
    else:
        if isinstance(resp, requests.Response):
            try:
                resp.raise_for_status()
            except requests.HTTPError as e:
                print(f"error: HTTP {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
                raise
            data = resp.json()
        else:
            data = resp

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render_text(data))

    if "usage" in data:
        u = data["usage"]
        print(
            f"--- tokens: prompt={u.get('prompt_tokens')} "
            f"completion={u.get('completion_tokens')} "
            f"reasoning={u.get('completion_tokens_details', {}).get('reasoning_tokens', 0)} ---",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
