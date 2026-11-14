"""All settings in one place.

Values come from environment variables so that nothing secret lives in the code.
The defaults are safe for running on your own laptop.
"""

import os


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


# ---- quiz
# How long players have to answer each question, in seconds.
QUESTION_SECONDS = _int("QUESTION_SECONDS", 20)

# Extra time the server still accepts an answer after the clock hits zero,
# to allow for a slow mobile network. Players never see this.
ANSWER_GRACE_SECONDS = 0.5

# Scoring: a correct answer is worth BASE_POINTS plus up to SPEED_BONUS
# depending on how quickly it came in. Wrong or missing answers score 0.
BASE_POINTS = 500
SPEED_BONUS = 500

MAX_NAME_LENGTH = 20
MAX_PLAYERS_PER_GAME = 60

# Finished or abandoned games are deleted after this many hours, so names and
# scores are not kept longer than needed.
GAME_TTL_HOURS = _int("GAME_TTL_HOURS", 12)

# ---- infrastructure
# Local default is a SQLite file. In production set DATABASE_URL to Postgres:
#   postgresql+psycopg://... (docker-compose builds it from deploy/.env on the server)
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///quiz.db")

# Which websites may open a socket to this server. Comma separated.
# In production this is the Cloudflare Pages address of the frontend.
CORS_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()
]
if "*" in CORS_ORIGINS:
    raise RuntimeError("CORS_ORIGINS must list exact origins, not '*'")

# Set to 1 when running behind Caddy, so the real client IP is read from
# X-Forwarded-For (Caddy overwrites that header, clients cannot fake it).
TRUST_PROXY = os.environ.get("TRUST_PROXY", "0") == "1"

PORT = _int("PORT", 5000)

# ---- abuse limits (per client IP unless noted)
# Each open socket holds one server thread (see Dockerfile: 512 threads), so the
# total is capped well below that: the server always has threads to spare and
# one attacker cannot freeze it for everyone.
MAX_CONNECTIONS_TOTAL = _int("MAX_CONNECTIONS_TOTAL", 400)
MAX_CONNECTIONS_PER_IP = _int("MAX_CONNECTIONS_PER_IP", 80)  # a class behind one school IP still fits
EVENTS_PER_SOCKET = (30, 10)  # at most 30 events per 10 seconds from one screen
EVENTS_PER_IP = (400, 10)  # and 400 per 10 seconds from one address (a whole class)
JOINS_PER_IP = (80, 60)  # at most 80 joins per minute
# One address can add at most this many players to ONE room in 10 minutes, so a
# single attacker cannot fill a class's room (60 places) with fake names.
JOINS_PER_IP_PER_ROOM = (_int("JOINS_PER_IP_PER_ROOM", 40), 600)
FAILED_LOOKUPS_PER_IP = (20, 60)  # wrong room codes / tokens: 20 per minute, then wait
CREATES_PER_IP = (10, 60)  # new rooms per minute
MAX_ACTIVE_GAMES = _int("MAX_ACTIVE_GAMES", 2000)  # rooms kept at once (old ones expire)
MAX_MESSAGE_BYTES = 4096  # largest socket message accepted
