# FinQuiz Live: a live classroom finance quiz

> **Live:**
> - **Teacher / projector:** https://finquizlive.pages.dev/host
> - **Students / phones:** https://finquizlive.pages.dev/ (or scan the QR code on the projector)

A teacher opens `/host` on the projector, students join on their phones with
the room code, and everyone plays five personal finance questions with a
20-second timer. The host screen shows the correct answer and a leaderboard
after each question, and the final ranking at the end.

## Architecture

```
 Phones / projector                Cloudflare Pages              AWS EC2 t3.micro (Docker Compose)
 ┌──────────────┐   HTTPS   ┌─────────────────────┐        ┌──────────────────────────────────────┐
 │ React + TS   │──────────▶│ static files + CSP  │        │ Caddy :443 (auto HTTPS, headers)     │
 │ (browser)    │           └─────────────────────┘        │   │ only /socket.io and /healthz     │
 │              │──── WSS (Socket.IO, polling fallback) ──▶│   ▼                                  │
 └──────────────┘                                          │ Flask + Socket.IO (gunicorn, 1 proc) │
                                                           │   │ private network, no public port  │
                                                           │   ▼                                  │
                                                           │ PostgreSQL 16 (volume)               │
                                                           └──────────────────────────────────────┘
```

| Part | Tech |
|---|---|
| Frontend | React 18 + TypeScript (Vite), Cloudflare Pages |
| Backend | Python 3.12, Flask + Flask-SocketIO, gunicorn |
| Database | PostgreSQL 16 (SQLite when running on a laptop) |
| Hosting | AWS EC2 t3.micro (1 GB + 2 GB swap), Docker Compose, Caddy for HTTPS |

## How the six rules are met

| Rule | How it is enforced | Where it is tested |
|---|---|---|
| **1. Answers stay on the server** | Questions exist only in `backend/questions.py`. The views in `game.py` add `correctIndex` and the explanation only once the question has closed. The timer runs on the server, and late answers are refused. Phones also get no score while a question is open, because a jump in score would give the answer away. CI checks that the built JS bundle contains no answers. | `test_open_question_views_never_contain_the_answer`, e2e "answer not sent before close" (records every byte each phone receives) |
| **2. Ten players at once** | Socket.IO starts on long-polling and upgrades to WebSocket, so it works on mobile data and strict Wi-Fi. One lock means simultaneous answers are counted once. A room update is built from one snapshot (3 queries, whatever the player count). The JS bundle is about 75 KB gzipped. The backend runs on always-on EC2, so it never sleeps. | e2e plays a full game with 10 real socket clients |
| **3. Refresh keeps the player** | A random token (in `localStorage`) is sent again on every reconnect, and the server restores the same player and score. Phones re-sync as soon as they come back from another app or a locked screen, and the screen is kept awake during the game. State lives in Postgres, and running timers restart after a server restart. | e2e: refresh mid-question, and a full server restart mid-game |
| **4. No frozen screens** | A status banner shows connecting / reconnecting / can't reach server + Retry. Every request times out after 8 seconds with a message and a Try again button. An error boundary covers render crashes, and `boot.js` covers a bundle that never loads. | manual: kill the backend while playing |
| **5. No secrets in the code** | Nothing in the repository is a secret, including CI, where Postgres uses trust auth. The DB password is generated on the server into git-ignored `deploy/.env`. **gitleaks** scans the whole git history in CI and in a pre-commit hook. | CI job "Secret scan" |
| **6. Scores are not public** | No HTTP route returns data (Caddy only exposes `/socket.io` and `/healthz`). The full leaderboard goes only to a socket that proved it holds the host token, and each phone gets only its own score and rank. Games are deleted after 12 hours. | `test_player_views_never_contain_other_players`, e2e probes URLs |

## Security hardening

- **Tokens:** 256-bit random host and player tokens, stored only as SHA-256 hashes and compared in constant time. A token works only in its own room.
- **Brute force:** wrong room codes or tokens are limited to 20 a minute per IP, then refused.
- **Abuse limits:**
  - **Events:** 30 per 10 s per connection, and 400 per 10 s per IP.
  - **Joins and rooms:** 80 joins and 10 new rooms a minute per IP, 60 players per room, at most 2,000 rooms at once.
  - **Messages:** 4 KB at most. A bigger one drops only the sender's connection.
- **No thread exhaustion:** every open socket holds a server thread. Connections are capped at 400 in total and 80 per IP, while gunicorn has 512 threads, so one attacker cannot freeze the server for a class.
- **Input:** codes are checked against a pattern, and choices must be a real integer from 0 to 3. React escapes names on screen.
- **Name spoofing:** names are NFKC-normalised and stripped of invisible and direction-override characters. Latin mixed with Cyrillic or Greek is refused. Duplicates are compared by how a name *looks* (case, accents, spaces and look-alike letters ignored), so nobody can join as a second "Asha".
- **Fake players:** one IP can add at most 40 players to one room in 10 minutes, so a single attacker cannot fill a class's room.
- **Shared devices:** saved host and player sessions expire on the device after 4 hours.
- **CORS:** sockets are accepted only from the exact frontend origin, and `*` is refused at startup.
- **Headers:** a strict CSP (`script-src 'self'`, connect only to our backend, no inline code), HSTS, `X-Frame-Options: DENY`, nosniff, no-referrer and Permissions-Policy, from Cloudflare (`dist/_headers`) and Caddy.
- **Containers:** they run as a non-root user with a read-only filesystem, all capabilities dropped, `no-new-privileges`, memory limits, log rotation and health checks. Postgres and the backend have no public port.
- **Supply chain:** Python dependencies are pinned exactly. `pip-audit`, `npm audit` and Dependabot run weekly.
- **Server:** security updates install automatically (`unattended-upgrades`). Ports 80 and 443 are open to everyone. Port 22 is open only to AWS EC2 Instance Connect (no SSH key exists for this server).

## Run it locally

```bash
# backend (terminal 1)
cd backend
python -m venv .venv
.venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python server.py              # http://localhost:5000

# frontend (terminal 2)
cd frontend
npm install
npm run dev                   # http://localhost:5173  (host screen: /host)
```

## Tests and checks

```bash
cd backend
pytest -q                        # 50 unit tests (game rules, name spoofing, what each screen may see)
python tests/e2e_check.py        # 60 end-to-end checks: real server, host + 10 players, attacks
ruff check . && pip-audit -r requirements.txt

cd ../frontend
npm run lint && npm run build && npm audit --omit=dev
```

CI (`.github/workflows/ci.yml`) runs all of the above on every push, plus a gitleaks scan of the whole history and the unit tests against real PostgreSQL.

## Common changes

- **Longer timer:** change `QUESTION_SECONDS` in `backend/config.py` (or in `deploy/.env` on the server) and restart the backend.
- **Add a question:** add a block to `QUESTIONS` in `backend/questions.py` with 4 `options`, `correct`, `explanation` and `source`, then restart the backend. The frontend needs no change.

## Deploy

### Backend on EC2
Quickest: launch the instance with `deploy/user-data.sh` as its *User data*. On first boot it installs Docker, clones this repo, writes `deploy/.env` with a random database password, and starts everything with HTTPS on `api.<ip-with-dashes>.sslip.io`. No SSH key is needed: use **EC2 Instance Connect** in the console for later changes.

Manual route:
1. Launch an Ubuntu 24.04 **t3.micro** (or t3.small) in `ap-south-1`:
   - Require IMDSv2.
   - Use a key pair for SSH (no passwords).
   - In the security group, open 22 to *your IP only*, plus 80 and 443 to everyone.
   - Attach an Elastic IP.
2. Add a DNS **A record** `api.yourdomain.com` pointing at that IP. On Cloudflare, set it to **DNS only (grey cloud)** so Caddy sees real client IPs for rate limits.
3. On the server, clone the repo and run `bash deploy/setup-ec2.sh` until it is done. It:
   - installs Docker and security updates,
   - creates `deploy/.env` with a random DB password,
   - asks you to set `API_DOMAIN` and `CORS_ORIGINS`.
4. Check: `curl https://api.yourdomain.com/healthz` should return `{"ok": true}`.

### Frontend on Cloudflare
```bash
cd frontend
VITE_SERVER_URL=https://api.<ip-with-dashes>.sslip.io npm run build   # also writes dist/_headers (CSP)
npx wrangler pages deploy                                              # settings in wrangler.jsonc
```
Cloudflare Pages serves `index.html` for unknown paths (there is no `404.html`), so `/host` works as a page.

## Project layout

```
backend/
  config.py      settings and limits, read from env vars
  questions.py   the five questions + source links
  db.py          tables: games, players, answers
  game.py        game rules + what each screen may see
  ratelimit.py   sliding-window rate limiter
  server.py      Flask + Socket.IO events, timers, broadcasting, limits
  tests/         unit tests (pytest) + end-to-end check
frontend/
  src/socket.ts          connection + call() with timeout
  src/useConnection.ts   status banner state, resume after reconnect / app switch
  src/useWakeLock.ts     keep the phone screen on during the game
  src/pages/             HostPage (projector), PlayerPage (phone)
  scripts/write-headers.mjs  security headers for Cloudflare
deploy/          docker-compose, Caddyfile, EC2 user-data (one-step setup), manual setup script
.github/         CI + Dependabot
```
