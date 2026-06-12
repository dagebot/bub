# MiMo Auto API reference

Source: <https://www.appinn.com/mimo-auto-free-api-guide-extract-from-mimo-code/>
The endpoint was extracted from the open-source **MiMo Code** terminal agent.
Use is unofficial — quotas and availability are not guaranteed.

## 1. Bootstrap (issue a short-lived JWT)

```
POST /api/free-ai/bootstrap
Content-Type: application/json

{"client": "your-unique-app-id"}
```

Response:

```json
{ "jwt": "<token>", "exp": 1700000000000 }
```

- `client` can be any string; treat it as your per-app identifier.
- `exp` is the **Unix time in milliseconds** when the JWT expires (~1h).
- Status codes: 200 OK, 429 rate-limited (back off), 5xx transient.

## 2. Chat Completions (OpenAI-compatible)

```
POST /api/free-ai/openai/chat
Content-Type: application/json
Authorization: Bearer <jwt>
X-Mimo-Source: mimocode-cli-free

{
  "model": "mimo-auto",
  "messages": [
    {"role": "system", "content": "You are a code reviewer."},
    {"role": "user",   "content": "Review this diff: ..."}
  ],
  "max_tokens": 4096,
  "stream": false
}
```

### Body fields (subset of OpenAI)

| Field | Notes |
| --- | --- |
| `model` | Always `"mimo-auto"`. Other model names are rejected. |
| `messages` | Standard OpenAI chat history. System + user + assistant. |
| `max_tokens` | Hard ceiling 128 000. |
| `temperature` | 0-2. |
| `stream` | `true` → SSE. |

### Response

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "Final answer …",
      "reasoning_content": "Chain of thought …"
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 252,
    "completion_tokens": 62,
    "total_tokens": 314,
    "completion_tokens_details": {"reasoning_tokens": 33}
  }
}
```

`reasoning_content` and `reasoning_tokens` are the only non-standard
additions. Everything else matches OpenAI's Chat Completions schema, so any
OpenAI client can be repointed at this endpoint with only the
`X-Mimo-Source` header added.

### Multimodal

Image inputs are accepted via the standard `image_url` content block (base64
data URI or HTTP URL). Output is text only.

## 3. Limits observed (best-effort, not contractual)

- 1 000 000 token context window
- 128 000 token output cap
- No published rate-limit; back off on `429`
- JWT TTL ~1 hour
- TLS-only; HTTP endpoints would fail

## 4. Error responses

| Code | Likely cause |
| --- | --- |
| 401 | Missing/invalid JWT or missing `X-Mimo-Source` header |
| 429 | Rate limited; back off and retry |
| 5xx | Transient; retry with exponential backoff |
