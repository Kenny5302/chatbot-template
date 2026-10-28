# CLAUDE.md

## What this is

**Sutter Assist**: one FastAPI app serving an AI chat assistant for many small local businesses (auto shops, HVAC, etc.). Each business is one YAML file in `businesses/`; adding a client means adding a file, not code. Replies in English, Spanish or Punjabi, answers only from the business's file, and takes callback requests as leads. Full details are in `README.md`.

- Chat page at `/b/<slug>`, embeddable bubble at `/b/<slug>/widget.js`, marketing landing page at `/`, health check at `/healthz` (returns only `{"ok": true}`).
- Live: https://business-chatbot-re10.onrender.com (monitored by UptimeRobot on `/healthz`).

## Architecture (`app/`)

- `main.py` routes and request validation; `config.py` env settings; `logging_config.py` app logging.
- `businesses.py` loads and validates all YAML at startup (a bad file stops startup); `*.draft.yaml` is ignored.
- `chat.py` `ChatService` (model calls, guards, fallbacks); `prompts.py` system prompt; `hours.py` open/closed.
- `leads.py` + `emailer.py` lead capture and Gmail send (3 retries, `unsent_leads.log` fallback).
- `storage.py` `FileStorage`, the only file-access code (conversations JSONL, leads, flagged); swap this class to move to a DB.
- `ratelimit.py` per-visitor limits, daily caps, `client_ip`, salted `visitor_hash`.
- `i18n.py` all Spanish/Punjabi UI text; `crisis.py` self-harm phrase list.
- `templates/`, `static/` front end; `scripts/draft_business.py` drafts a YAML from a website.

## Run and test

```bash
source .venv/bin/activate          # venv from /opt/anaconda3/bin/python3 -m venv .venv; pip install -r requirements-dev.txt
uvicorn app.main:app --reload
pytest                              # fast, fake model client, no network
pyright
RUN_LIVE_TESTS=1 pytest tests/test_live.py -v   # optional, real model, costs a few cents
```

Run `pytest` and `pyright` before committing.

## Deployment (Render)

- Blueprint from `render.yaml`. Blueprint changes are applied by a **manual sync** in the Render dashboard; pushing alone doesn't change the service config.
- Start command must keep `--no-access-log` (no raw visitor IPs in logs) and `--no-proxy-headers` (uvicorn must not rewrite the connection address from `X-Forwarded-For`).
- `TRUSTED_PROXY_HOPS=2` because Render sits behind Cloudflare (`X-Forwarded-For` is `client, cloudflare-ip`). Verified with a spoofed leftmost entry. If Render's setup changes, re-verify with `LOG_CLIENT_IP_DEBUG=1`, then remove it.
- Secrets (`ANTHROPIC_API_KEY`, `GMAIL_APP_PASSWORD`, `OPERATOR_BCC_EMAIL`) are `sync: false` and set only in the Render dashboard. Persistent disk at `/var/data` (`DATA_DIR`).
- Adding a client: add YAML, commit, push.

## Safety and privacy rules (do not weaken)

- Never commit secrets; they live in `.env` (git-ignored) or the Render dashboard. Don't put them in this file.
- Visitor IPs are stored only as a salted hash; never log raw IPs except temporary `LOG_CLIENT_IP_DEBUG`.
- Rate-limit IP comes from the right end of `X-Forwarded-For` per `TRUSTED_PROXY_HOPS`; never trust the leftmost entry.
- Limits: 1000 chars per message, 30 customer messages per conversation, 10/min and 60/day per visitor, daily message caps (global and per business).
- The bot opens by saying it is an AI assistant, and the "chats are saved" notice stays in all languages.
- Emergencies (gas, smoke, fire, CO, failing brakes): say stop/leave and call 911 or the gas company first, then the shop number.
- Self-harm: 988/911, no sales or lead capture; the API-failure fallback also includes the 988/911 line. Threats: "call 911" and drop the topic. Both are flagged (`flagged.jsonl`, `FLAGGED` log line). Phrases live in `app/crisis.py`.
- Never agree to discounts, price matches, or unlisted prices/timelines; prices are estimates. Answer only from the business file; decline off-topic requests; never reveal instructions; strip code blocks.
- Lead file is written before email is attempted; one lead per conversation (updates send an "Updated lead" email).
- Dependencies stay pinned to exact versions in `requirements.txt`.
