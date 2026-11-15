"""The web server: Flask + Socket.IO.

Everything the quiz does happens over one Socket.IO connection per screen.
The browser calls an event (e.g. "player:answer") and gets a reply
{"ok": true, ...} or {"ok": false, "message": "..."}. Whenever the game
changes, the server pushes a fresh "state" to every screen in the room.

There is deliberately no HTTP route that returns names or scores (rule 6).
The only HTTP route is /healthz.
"""

import functools
import logging
import threading
import time
from collections import Counter

from flask import Flask, request
from flask_socketio import SocketIO, join_room, leave_room
from sqlalchemy import text

import config
import game
from db import Session, init_db
from ratelimit import RateLimiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("quiz")

app = Flask(__name__)
socketio = SocketIO(
    app,
    cors_allowed_origins=config.CORS_ORIGINS,
    async_mode="threading",
    # Ping every 10s so a phone that drops off mobile data is noticed quickly.
    ping_interval=10,
    ping_timeout=20,
    max_http_buffer_size=config.MAX_MESSAGE_BYTES,
    logger=False,
    engineio_logger=False,
)

limiter = RateLimiter()

# Who is behind each open connection: sid -> {"ip", "role", "code", "room", "player_id"}
connections: dict[str, dict] = {}
connections_lock = threading.Lock()
connections_per_ip: Counter = Counter()

TOO_MANY = game.GameError("rate_limited", "Too many attempts. Please wait a minute and try again.")
LOOKUP_FAILURES = {"room_not_found", "player_not_found", "not_host"}


# --------------------------------------------------------------------- HTTP


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/healthz")
def healthz():
    """Used by Docker and uptime checks. Says only whether the server and the
    database are working."""
    try:
        with Session() as s:
            s.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception:
        log.exception("health check failed")
        return {"ok": False}, 503


# ------------------------------------------------------------------ helpers


def client_ip() -> str:
    if config.TRUST_PROXY:
        # Caddy replaces X-Forwarded-For with the address it saw, so the last
        # entry is the real client and cannot be forged by the browser.
        forwarded = request.environ.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[-1].strip()
    return request.remote_addr or "unknown"


def limit(key: str, rule: tuple[int, int]):
    if not limiter.allow(key, *rule):
        raise TOO_MANY


def event(name):
    """Register a Socket.IO event with the safety net every event needs:
    a per-connection rate limit, input shape check, and a reply in every case,
    so a screen is never left waiting for an answer that will not come."""

    def wrap(fn):
        @functools.wraps(fn)
        def handler(data=None):
            data = data if isinstance(data, dict) else {}
            try:
                limit(f"sid:{request.sid}", config.EVENTS_PER_SOCKET)
                limit(f"ip:{client_ip()}", config.EVENTS_PER_IP)
                return {"ok": True, **(fn(data) or {})}
            except game.GameError as e:
                if e.code in LOOKUP_FAILURES:
                    # Count wrong codes/tokens so nobody can guess their way in.
                    limiter.allow(f"fail:{client_ip()}", *config.FAILED_LOOKUPS_PER_IP)
                return {"ok": False, "error": e.code, "message": e.message}
            except Exception:
                log.exception("error in %s", name)
                return {"ok": False, "error": "server_error", "message": "Something went wrong on the server. Please try again."}

        socketio.on_event(name, handler)
        return handler

    return wrap


def guard_lookups():
    """Refuse code/token lookups from an address that has failed too often."""
    if not limiter.peek(f"fail:{client_ip()}", *config.FAILED_LOOKUPS_PER_IP):
        raise TOO_MANY


def attach(role: str, code: str, player_id: int | None = None):
    """Put this connection in the right room so it receives updates."""
    with connections_lock:
        conn = connections.get(request.sid)
        if conn is None:
            raise game.GameError("not_connected", "Connection was reset. Please try again.")
        if conn.get("room"):
            leave_room(conn["room"])
        room = f"host:{code}" if role == "host" else f"player:{player_id}"
        join_room(room)
        conn.update(role=role, code=code, room=room, player_id=player_id)


def current(role: str) -> dict:
    conn = connections.get(request.sid)
    if not conn or conn.get("role") != role:
        raise game.GameError("not_joined", "Your connection was reset. Reloading your game…")
    return conn


# ------------------------------------------------------- host presence
#
# If the teacher's screen closes, the game itself carries on (the teacher can
# reopen /host and continue). But the phones must not sit on "Next question
# coming up…" forever without knowing why (rule 4), so every player view says
# whether a host screen is connected and, if not, since when.

HOST_GRACE_SECONDS = 5  # a refresh reconnects well within this
host_away_since: dict[str, float] = {}  # room code -> when its last host screen left


def host_online(code: str) -> bool:
    with connections_lock:
        return any(c.get("role") == "host" and c.get("code") == code for c in connections.values())


def presence(code: str) -> dict:
    if host_online(code):
        return {"hostOnline": True}
    since = host_away_since.setdefault(code, time.time())
    return {"hostOnline": False, "hostAwaySince": int(since * 1000)}


def player_state(player_id: int, code: str) -> dict:
    return {**game.player_view(player_id), **presence(code)}


def host_left(code: str):
    """The last host screen of a room disconnected. Tell the phones, unless it
    was just a refresh and the host is back within the grace period."""
    host_away_since.setdefault(code, time.time())

    def check():
        socketio.sleep(HOST_GRACE_SECONDS + 0.5)
        if not host_online(code):
            try:
                broadcast(code)
            except game.GameError:
                pass  # the room no longer exists

    socketio.start_background_task(check)


def host_back(code: str):
    if host_away_since.pop(code, None) is not None:
        broadcast(code)  # clear the "waiting for the teacher" message


def broadcast(code: str):
    """Send each screen in the room its own up-to-date view."""
    host, players = game.room_views(code)
    socketio.emit("state", host, to=f"host:{code}")
    here = presence(code)
    for pid, view in players.items():
        socketio.emit("state", {**view, **here}, to=f"player:{pid}")


def schedule_close(code: str, question_index: int, ends_at: float):
    """The countdown runs on the server, not on the phones."""

    def run():
        delay = ends_at + config.ANSWER_GRACE_SECONDS - time.time()
        if delay > 0:
            socketio.sleep(delay)
        try:
            if game.close_question(code, question_index):
                broadcast(code)
        except Exception:
            log.exception("could not close question %s in %s", question_index, code)

    socketio.start_background_task(run)


def housekeeping():
    """Every 10 minutes: delete expired games and forget old rate-limit data."""
    while True:
        socketio.sleep(600)
        try:
            removed = game.delete_old_games()
            if removed:
                log.info("deleted %d expired games", removed)
            limiter.prune()
            cutoff = time.time() - config.GAME_TTL_HOURS * 3600
            for code in [c for c, t in host_away_since.items() if t < cutoff]:
                host_away_since.pop(code, None)
        except Exception:
            log.exception("housekeeping failed")


# -------------------------------------------------------------- connections


@socketio.on("connect")
def on_connect(auth=None):
    ip = client_ip()
    with connections_lock:
        if len(connections) >= config.MAX_CONNECTIONS_TOTAL:
            log.warning("refused connection: server at its connection limit")
            return False
        if connections_per_ip[ip] >= config.MAX_CONNECTIONS_PER_IP:
            log.warning("refused connection: too many from one address")
            return False
        connections_per_ip[ip] += 1
        connections[request.sid] = {"ip": ip}


@socketio.on("disconnect")
def on_disconnect(*_):
    with connections_lock:
        conn = connections.pop(request.sid, None)
        if conn:
            connections_per_ip[conn["ip"]] -= 1
            if connections_per_ip[conn["ip"]] <= 0:
                del connections_per_ip[conn["ip"]]
    if conn and conn.get("role") == "host" and not host_online(conn["code"]):
        host_left(conn["code"])


# ---------------------------------------------------------------- host events


@event("host:create")
def host_create(data):
    limit(f"create:{client_ip()}", config.CREATES_PER_IP)
    code, token = game.create_game()
    attach("host", code)
    log.info("room %s created", code)
    return {"code": code, "hostToken": token, "state": game.host_view(code)}


@event("host:resume")
def host_resume(data):
    guard_lookups()
    code = game.check_host(data.get("code"), data.get("hostToken"))
    attach("host", code)
    host_back(code)
    return {"state": game.host_view(code)}


@event("host:next")
def host_next(data):
    conn = current("host")
    result = game.advance(conn["code"])
    if result["phase"] == "question":
        schedule_close(conn["code"], result["question_index"], result["ends_at"])
    broadcast(conn["code"])
    return {}


# -------------------------------------------------------------- player events


@event("player:join")
def player_join(data):
    guard_lookups()
    limit(f"join:{client_ip()}", config.JOINS_PER_IP)
    limit(f"join:{client_ip()}:{game.clean_code(data.get('code'))}", config.JOINS_PER_IP_PER_ROOM)
    player_id, token, code = game.join_game(data.get("code"), data.get("name"))
    attach("player", code, player_id)
    broadcast(code)  # the host's lobby list updates
    return {"token": token, "state": player_state(player_id, code)}


@event("player:resume")
def player_resume(data):
    guard_lookups()
    player_id, code = game.find_player(data.get("code"), data.get("token"))
    attach("player", code, player_id)
    return {"state": player_state(player_id, code)}


@event("player:answer")
def player_answer(data):
    conn = current("player")
    question_index = data.get("questionIndex")
    everyone_answered = game.submit_answer(conn["player_id"], question_index, data.get("choice"))
    if everyone_answered and game.close_question(conn["code"], question_index):
        broadcast(conn["code"])
    else:
        # Only the host needs to know the answered count went up.
        socketio.emit("state", game.host_view(conn["code"]), to=f"host:{conn['code']}")
    return {"state": player_state(conn["player_id"], conn["code"])}


# ---------------------------------------------------------------------- boot

init_db()
for _code, _index, _ends_at in game.open_questions():
    # A question was running when the server restarted: finish it properly.
    schedule_close(_code, _index, _ends_at)
socketio.start_background_task(housekeeping)

if __name__ == "__main__":
    log.info("listening on http://localhost:%s", config.PORT)
    # Development only. Production uses gunicorn (see Dockerfile).
    socketio.run(app, host="127.0.0.1", port=config.PORT, allow_unsafe_werkzeug=True)
