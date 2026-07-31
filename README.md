# ChattySup

A lightweight, self-hosted helpdesk — a simpler take on Chatwoot. One Python
process, one SPA, SQLite by default, Telegram as the first channel and a
pluggable source architecture for everything that comes next.

```
┌──────────┐   ┌──────────────┐   ┌───────────────┐   ┌──────────────┐
│ Sidebar  │   │ Conversations│   │     Chat      │   │   Contact    │
│ inboxes  │   │ mine/unassig.│   │ media, notes, │   │ attributes,  │
│ labels   │   │ filters      │   │ voice, react. │   │ macros, past │
└──────────┘   └──────────────┘   └───────────────┘   └──────────────┘
```

## Features

**Inbox**
- Multi-source conversation list with filters (status, inbox, assignee, labels,
  priority, full-text search) and Mine / Unassigned / All tabs
- Chat with images, video, files, stickers, voice messages (record & play with a
  waveform), locations, replies, message reactions and edits
- Private notes, canned responses (`/shortcut`), signatures, typing indicators
- Assignment to agents and teams, priorities, labels, snooze / resolve / reopen
- Live updates over WebSocket

**Contacts**
- Searchable directory, editable profile and custom attributes, notes timeline,
  conversation history, block / unblock

**Administration**
- Inboxes: add / edit / delete any channel with a form generated from the
  channel definition, connection health, per-inbox proxy, polling or webhook
- Agents, teams, labels, canned responses
- Automations: condition/action rules plus per-inbox auto-greeting and
  out-of-office replies with working hours
- Outgoing webhooks (HMAC-signed, native or Chatwoot format), API tokens,
  SSO (OIDC) providers
- Installation settings, registration flag, dashboard with live stats

**Chatwoot compatibility**
- Outgoing webhooks in Chatwoot's exact payload format and event vocabulary
- An `api` channel: an inbox fed over HTTP, replies posted to your webhook_url
- Chatwoot's Client API (`/public/api/v1/…`) and a subset of the Application
  API (`/api/v1/accounts/…`) — see [docs/CHATWOOT-COMPAT.md](docs/CHATWOOT-COMPAT.md)

**Telegram**
- Latest Bot API, long polling or webhook mode, optional HTTP/SOCKS proxy
- Text, photos, video, video notes, audio, voice, documents, animations,
  stickers, locations, contacts, polls, replies, edits, deletions and reactions
  in both directions

## Quick start

```bash
git clone <this repo> && cd chattysup
cp .env.example .env          # set SECRET_KEY and BASE_URL

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload            # http://localhost:8000

# Frontend (separate shell, dev mode with hot reload)
cd frontend
npm install
npm run dev                              # http://localhost:5173
```

Open the app: because no user exists yet, the **registration screen is shown
automatically** and the account you create becomes the super admin. Afterwards
signup stays closed unless you enable it (`ENABLE_REGISTRATION=true` or
Settings → Registration).

For a single-process deployment, build the SPA into the backend and run only
uvicorn:

```bash
cd frontend && npm run build     # emits into backend/app/static
cd ../backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Docker

```bash
cp .env.example .env
docker compose up -d --build     # app on :8000, Postgres alongside
```

## Connecting Telegram

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Settings → Inboxes → **Add inbox** → Telegram.
3. Paste the token, choose a mode:
   - **Long polling** — works behind NAT, no public URL needed.
   - **Webhook** — needs `BASE_URL` to be reachable over HTTPS; ChattySup
     registers `\{BASE_URL}/api/v1/webhooks/telegram/{token}` for you.
4. Optionally set a proxy (`http://user:pass@host:3128`, `socks5://…`) — it is
   used for every call of that inbox only.
5. Optionally enable the auto-greeting and working hours.

Write to the bot; the conversation appears in the inbox immediately.

## Configuration

All settings come from the environment (see [`.env.example`](.env.example)):

| Variable | Default | Meaning |
| --- | --- | --- |
| `BASE_URL` | `http://localhost:8000` | Public URL, used for webhook callbacks |
| `SECRET_KEY` | random per boot | JWT signing key — **set it in production** |
| `ENABLE_REGISTRATION` | `false` | Self-service signup (first user always allowed) |
| `DATABASE_URL` | SQLite file | `postgresql+asyncpg://…` for Postgres |
| `STORAGE_PATH` | `backend/storage` | Where attachments are written |
| `MAX_UPLOAD_SIZE` | 50 MB | Upload limit |
| `HTTP_PROXY` | – | Default proxy for channels without their own |
| `RUN_WORKERS` | `true` | Run channel pollers in the API process |
| `CORS_ORIGINS` | `*` | Comma separated allowed origins |

To scale the pollers out of the API process, set `RUN_WORKERS=false` and run
`python -m app.workers.runner` as a second service.

## Architecture

```
backend/app
├── main.py            FastAPI app, SPA hosting, lifespan
├── config.py db.py    settings, async engine, session
├── models/            SQLAlchemy 2.0 domain model
├── serializers.py     the single response shape (REST = WebSocket = webhooks)
├── core/              security, deps, event bus + WebSocket manager, storage
├── channels/          ⇦ pluggable sources
│   ├── base.py          BaseChannel, FieldSpec, normalised payloads, registry
│   └── telegram/        Bot API client + normalisation
├── services/          conversations, attachments, automation, webhooks, settings
├── api/v1/            REST routers
└── workers/           polling supervisor, scheduler, standalone runner
frontend/src
├── lib/               api client, types, reconnecting WebSocket, formatting
├── store/             auth + shared app data contexts
├── components/        UI kit, layout, conversation panes
└── pages/             login, conversations, contacts, admin
```

Adding a new source is a single class — see
[docs/CHANNELS.md](docs/CHANNELS.md). Automations, greetings and webhooks are
documented in [docs/AUTOMATIONS.md](docs/AUTOMATIONS.md), and the Chatwoot
compatibility layer in [docs/CHATWOOT-COMPAT.md](docs/CHATWOOT-COMPAT.md). The REST API is
self-documenting at `/api/docs`.

## Tests

```bash
cd backend && pip install -r requirements-dev.txt && python -m pytest -q
cd frontend && npx tsc --noEmit
```

To explore the UI without connecting a real bot, load the demo dataset:

```bash
cd backend && python scripts/seed_demo.py    # demo@chattysup.local / demo1234
```

## License

MIT
