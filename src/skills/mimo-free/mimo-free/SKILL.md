---
name: mimo-free
description: |
  Backup LLM provider for Bub using Xiaomi's free MiMo Auto API (extracted from MiMo Code).
  Use ONLY as a fallback when other providers are unavailable: (1) 1M context window
  and 128K output make MiMo Auto useful for summarizing long documents or large
  diffs, (2) the endpoint is unofficial (extracted via DevTools from MiMo Code),
  unauthenticated third-party use is at the operator's own risk, and (3) the JWT
  expires ~1 hour so this is not suitable for long-running or production traffic.
metadata:
  channel: llm-fallback
---

# MiMo Free (Backup LLM Provider)

## Overview

Wraps the **MiMo Auto** Chat Completions endpoint exposed by Xiaomi's free
MiMo Code service. The endpoint is OpenAI-compatible and returns a
`reasoning_content` field alongside the standard `content`, which is useful
when Bub needs to show its work or surface chain-of-thought to the user.

This skill is **stand-alone** — it does not register MiMo as a Bub provider or
intercept model selection. Call it explicitly via the `scripts/mimo_chat.py`
helper when other providers are unavailable and a 1M-context model is wanted.

## When to use

- Primary LLM provider is rate-limited, 5xx-ing, or otherwise unreachable.
- The task is summarization or analysis of long content (MiMo supports a 1M
  context window and 128K output).
- You explicitly want a free fallback that does not consume Bub's paid
  provider quota.

**Do NOT use for production traffic.** The JWT expires in ~1 hour, the
endpoint is undocumented and may stop working without notice, and
unauthenticated scraping of MiMo Code may violate Xiaomi's terms of service.

## Quick start

```bash
# Send a prompt and print the assistant reply
uv run ./scripts/mimo_chat.py "Explain RISC-V in 3 sentences"

# Read prompt from stdin (heredoc-safe)
uv run ./scripts/mimo_chat.py --system "You are a code reviewer." <<'EOF'
Review this diff for correctness and style:

```diff
+    print("hello")
```
EOF

# JSON output (full OpenAI response object, for piping to jq)
uv run ./scripts/mimo_chat.py --json "Hello"

# Force a fresh JWT (skip cache)
uv run ./scripts/mimo_chat.py --no-cache "Hello"
```

## Endpoints

| Purpose | Method | URL |
| --- | --- | --- |
| Bootstrap (get JWT) | `POST` | `https://api.xiaomimimo.com/api/free-ai/bootstrap` |
| Chat Completions    | `POST` | `https://api.xiaomimimo.com/api/free-ai/openai/chat` |

## Required headers (chat only)

| Header | Value | Notes |
| --- | --- | --- |
| `Authorization` | `Bearer <jwt>` | Token from bootstrap |
| `X-Mimo-Source` | `mimocode-cli-free` | **Required** — without it the API returns 401 |

## Gotchas

- Chat path is `/openai/chat` — **not** `/openai/chat/completions`.
- `client` body param can be any unique string; use a stable per-app value so
  rate-limits don't bleed across users.
- JWT is cached at `/tmp/bub-mimo-jwt` (mode 0600) for the remaining lifetime.
- Streaming: pass `--stream` to receive SSE chunks; default is non-streaming JSON.

## Environment variables

| Var | Default | Purpose |
| --- | --- | --- |
| `BUB_MIMO_BASE_URL` | `https://api.xiaomimimo.com` | Override for testing |
| `BUB_MIMO_CLIENT`   | `bub-agent` | Value sent as the `client` bootstrap field |
| `BUB_MIMO_CACHE`    | `/tmp/bub-mimo-jwt` | Where the JWT is cached |

## Resources

### scripts/

- `mimo_chat.py` — single-shot Chat Completions helper. Bootstraps a JWT,
  sends the request, prints the reply (or full JSON with `--json`).

### references/

- `api.md` — full request/response schemas, error codes, and rate-limit
  notes.
