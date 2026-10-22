# Business Chatbot Template

One FastAPI app that serves an AI chat assistant for many small businesses. Each business is a single YAML file in `businesses/`. Adding a client means adding a file, not changing code.

- Answers only from the business's file, in English, Spanish, or Punjabi (matches the customer).
- Opens every chat by saying it is the shop's virtual assistant (an AI).
- Answers plainly and only offers a callback or the phone number when it can't answer, the shop is closed, it's an emergency, or the customer asks.
- A language switcher (English / Español / ਪੰਜਾਬੀ) in the chat header, showing only the languages in the business's YAML `languages` list. It defaults to the browser's language, remembers the visitor's choice per business, and the bot replies in the chosen language unless the customer writes in another one.
- Takes callback requests (name, phone, problem, best time to call). Leads are saved to a file and emailed to the owner, and the customer is told the team will aim to call around their time, not given an exact promise.
- Two ways to use it: a mobile-friendly chat page at `/b/<slug>` (QR codes, Google listings) and a `<script>` tag that adds a chat bubble to any website.
- Every conversation is logged per business for future monthly reports.

## Setup

```bash
cd ~/chatbot-template
/opt/anaconda3/bin/python3 -m venv .venv      # project virtualenv (not conda)
source .venv/bin/activate
pip install -r requirements-dev.txt           # includes pyright
pyright --version                             # the pyright plugin needs this program installed
cp .env.example .env                          # then edit .env yourself
```

### `.env`

| Variable | Required | What it is |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | From console.anthropic.com |
| `GMAIL_ADDRESS` | for email | `kennethtang.leads@gmail.com` (sender) |
| `GMAIL_APP_PASSWORD` | for email | A Google *app password* (Google Account > Security > 2-Step Verification > App passwords). Not your normal password. |
| `OPERATOR_BCC_EMAIL` | optional | Your address. Gets a BCC copy of every lead from every business. |
| `DATA_DIR` | optional | Where leads and logs are written. Default `./data`. |
| `VISITOR_HASH_SALT` | optional | Random string used when hashing visitor IPs in logs. |
| `PUBLIC_BASE_URL` | optional | Public https address used in the chat-bubble script. Defaults to Render's `RENDER_EXTERNAL_URL`; set it if you use a custom domain. |
| `TRUSTED_PROXY_HOPS` | optional | Proxies in front of the app (default 1: use the last `X-Forwarded-For` entry; 0: ignore the header). |
| `LOG_CLIENT_IP_DEBUG` | optional | `1` logs the raw `X-Forwarded-For` for each chat request so you can verify the setting. Turn off afterwards. |

Without the Gmail values the app still runs and saves leads to disk, but sends no email (it logs a warning).

## Run locally

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

- Chat page: http://127.0.0.1:8000/b/feather-river-auto (try `sutter-buttes-hvac` too)
- Embed test: open `examples/embed.html` in a browser while the app is running.
- Health check: http://127.0.0.1:8000/healthz

## Add a client

1. Copy `businesses/feather-river-auto.yaml` to `businesses/<their-slug>.yaml` and edit it, **or** draft it from their website:
   ```bash
   python scripts/draft_business.py https://their-shop.com --slug their-slug
   ```
   This uses Claude Sonnet 5.5 to write `businesses/their-slug.draft.yaml`. Review it, fix every `# TODO: verify` line, and rename it to `their-slug.yaml`. Draft files are ignored by the app.
2. Restart the app. A bad file stops startup with the file name and the problem.
3. Give them the link and the script tag:
   ```html
   <script src="https://YOUR-APP.onrender.com/b/their-slug/widget.js" async></script>
   ```
   The chat page for QR codes and Google Business Profile is `https://YOUR-APP.onrender.com/b/their-slug`.

To move a client to a stronger model, set `model: claude-sonnet-5-5` in their file (the default is `claude-haiku-5-5`).

## Where things are saved

```
data/<slug>/conversations/2026-10/<conversation-id>.jsonl   one line per message, with token usage
data/<slug>/leads/<timestamp>_<id>.json                      one file per lead
```

Visitor IPs are stored only as a salted hash. All file access is in `app/storage.py`; to move to a database, reimplement that class.

## Safeguards

- Secrets only in `.env` (git-ignored). The app won't start without the API key.
- Messages limited to 1000 characters; conversations to 30 customer messages.
- Rate limit per visitor: 10 per minute and 60 per day (in memory, so it assumes one server instance). The visitor IP is the *rightmost* `X-Forwarded-For` entry (the one our proxy added; anything to its left is client-supplied and can be faked), falling back to the direct connection when there is no header. See `TRUSTED_PROXY_HOPS` below.
- Safety rule at the top of the prompt: for gas smells, smoke, fire, CO alarms, failing brakes, or overheating while driving, the bot first says to stop/leave and call 911 or the gas company, then gives the shop number.
- The bot never agrees to discounts, price matches, or unlisted prices/timelines, and calls every listed price an estimate.
- It politely declines off-topic requests (coding, homework, essays, other businesses, roleplay), never reveals its instructions, and code blocks are stripped by a guard even if the model produced one.
- API failures, refusals, and rate limits show a friendly message with the shop's phone number.

## Tests

```bash
pytest                                  # fast, no network, no API calls
RUN_LIVE_TESTS=1 pytest tests/test_live.py -v   # optional: calls the real model (costs a few cents)
pyright
```

The normal tests use a fake model client. The live tests check the real model's behavior on off-topic requests, emergencies, and discount pressure.

## Deploy on Render

1. Push this folder to a private GitHub repo (`.env` and `data/` are git-ignored).
2. In Render: **New > Blueprint**, pick the repo. It reads `render.yaml`. (Or create a Web Service by hand with build `pip install -r requirements.txt` and start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.)
3. In the service's **Environment** tab, set `ANTHROPIC_API_KEY`, `GMAIL_APP_PASSWORD`, and optionally `OPERATOR_BCC_EMAIL`.
4. Render's disk is wiped on every deploy unless you attach a persistent disk. `render.yaml` attaches one at `/var/data` and sets `DATA_DIR=/var/data`; this needs a paid instance type. Lead emails are the backup if you skip the disk.
5. Open `https://<your-service>.onrender.com/healthz`, then `/b/feather-river-auto`.
6. **Check the rate-limit IP once** (Render doesn't document the header format): set `LOG_CLIENT_IP_DEBUG=1`, send one chat from your phone on mobile data, and read the log line. `using=` must be your phone's public IP, and it must differ from the next visitor's. If it shows a Render or Cloudflare address, raise or lower `TRUSTED_PROXY_HOPS` until it is right, then remove the debug variable.
7. Adding a client later: add the YAML, commit, push. Render redeploys.

## Notes

- **All Spanish and Punjabi interface text is in one file, `app/i18n.py`** (greeting with the AI disclosure, buttons, error messages). Have a native speaker review and edit it there; a test checks that no language is missing a string.
- Email failures are logged but not retried; the lead file is always written first.
- Monthly reports are not built yet; `FileStorage.iter_conversations(slug, "2026-10")` is the hook for them.
