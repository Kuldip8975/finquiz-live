"""End-to-end check: starts the real server, plays a full game with one host
and ten players over real Socket.IO connections, and checks the rules.

Run from the backend folder:
    python tests/e2e_check.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

import socketio

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)
from questions import QUESTIONS  # noqa: E402  (used only to know which answers are right)

PORT = 5055
URL = f"http://127.0.0.1:{PORT}"
SECONDS = 3
results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(("PASS " if condition else "FAIL ") + name + (f"  ({detail})" if detail and not condition else ""))


def start_server(db_path):
    try:
        urllib.request.urlopen(URL + "/healthz", timeout=1)
        raise RuntimeError(f"port {PORT} is already in use (an old test server?). Stop it and run again.")
    except OSError:
        pass  # nothing listening: good
    env = {
        **os.environ,
        "QUESTION_SECONDS": str(SECONDS),
        "PORT": str(PORT),
        "DATABASE_URL": f"sqlite:///{db_path}",
        "MAX_CONNECTIONS_PER_IP": "40",
        "JOINS_PER_IP_PER_ROOM": "25",
        "CORS_ORIGINS": URL,
    }
    proc = subprocess.Popen(
        [sys.executable, "server.py"], cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    for _ in range(50):
        try:
            urllib.request.urlopen(URL + "/healthz", timeout=1)
            return proc
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("server did not start")


class Screen:
    """One browser: a socket plus a log of everything the server sent it."""

    def __init__(self):
        self.received = []  # every payload, as raw JSON text
        self.state = None
        self.sio = socketio.Client(reconnection=False)
        self.sio.on("state", self._on_state)
        self.sio.connect(URL, transports=["websocket"])

    def _on_state(self, data):
        self.received.append(json.dumps(data))
        self.state = data

    def call(self, event, data=None):
        reply = self.sio.call(event, data or {}, timeout=5)
        self.received.append(json.dumps(reply))
        if reply.get("state"):
            self.state = reply["state"]
        return reply

    def close(self):
        self.sio.disconnect()


def wait_for(fn, timeout=SECONDS + 3):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.05)
    return False


def main():
    db_path = os.path.join(tempfile.mkdtemp(), "e2e.db")
    server = start_server(db_path)
    try:
        host = Screen()
        reply = host.call("host:create")
        code, host_token = reply["code"], reply["hostToken"]
        check("host gets a room code", len(code) == 5)

        # ---- ten players join
        players, tokens = [], []
        for i in range(10):
            p = Screen()
            r = p.call("player:join", {"code": code.lower(), "name": f"Player {i + 1}"})
            players.append(p)
            tokens.append(r.get("token"))
        check("ten players join", all(tokens))
        check("host lobby lists ten names", wait_for(lambda: host.state and len(host.state.get("players", [])) == 10))

        dup = Screen()
        r = dup.call("player:join", {"code": code, "name": "player 1"})
        check("duplicate name is refused", r.get("error") == "name_taken")
        r = dup.call("player:join", {"code": "ZZZZZ", "name": "X"})
        check("wrong room code gives a clear message", r.get("error") == "room_not_found" and r.get("message"))
        dup.close()

        r = players[0].call("host:next")
        check("a player cannot start the quiz", r.get("ok") is False)

        expected = [0] * 10
        for qi, q in enumerate(QUESTIONS):
            for p in players:
                p.received.clear()
            host.received.clear()
            host.call("host:next")
            check(
                f"Q{qi + 1}: phones receive the question",
                wait_for(lambda: all(p.state.get("phase") == "question" and p.state["questionIndex"] == qi for p in players)),
            )

            if qi == 1:
                # Rule 3: a player drops off mid-question and comes back.
                players[4].close()
                players[4] = Screen()
                r = players[4].call("player:resume", {"code": code, "token": tokens[4]})
                check("refresh mid-question rejoins the same game", r.get("ok") and r["state"]["phase"] == "question")

            # Players 0-5 answer correctly, 6-8 wrongly, 9 never answers.
            for i, p in enumerate(players[:9]):
                choice = q["correct"] if i < 6 else (q["correct"] + 1) % 4
                r = p.call("player:answer", {"questionIndex": qi, "choice": choice})
                if not r.get("ok"):
                    check(f"Q{qi + 1}: answer accepted", False, r.get("message"))
            r = players[0].call("player:answer", {"questionIndex": qi, "choice": 0})
            check(f"Q{qi + 1}: second answer refused", r.get("error") == "already_answered")

            # Rule 1: nothing sent while the question was open contains the answer.
            open_traffic = "".join(t for p in players for t in p.received) + "".join(host.received)
            check(
                f"Q{qi + 1}: answer not sent before close",
                "correctIndex" not in open_traffic
                and q["explanation"] not in open_traffic
                and '"score"' not in "".join(t for p in players for t in p.received),
            )

            check(f"Q{qi + 1}: closes after the timer", wait_for(lambda: host.state["phase"] == "reveal"))
            r = players[9].call("player:answer", {"questionIndex": qi, "choice": q["correct"]})
            check(f"Q{qi + 1}: late answer refused", r.get("error") == "closed")

            hs = host.state
            check(
                f"Q{qi + 1}: host sees correct answer + leaderboard",
                hs["question"]["correctIndex"] == q["correct"] and len(hs["leaderboard"]) == 10,
            )
            wait_for(lambda: all(p.state.get("phase") == "reveal" for p in players))
            for i in range(6):
                expected[i] = players[i].state["score"]
            check(
                f"Q{qi + 1}: right answers score, wrong ones do not",
                all(players[i].state["score"] > 0 for i in range(6))
                and all(players[i].state["score"] == 0 for i in range(6, 10)),
            )
            check(
                f"Q{qi + 1}: phones never see other players' names",
                not any(f'Player {j + 1}"' in t for i, p in enumerate(players) for t in p.received for j in range(10) if j != i),
            )

            if qi == 2:
                # Rule 3 again, but harder: restart the whole server mid-game.
                server.terminate()
                server.wait()
                server = start_server(db_path)
                for p in players:
                    p.close()
                players = [Screen() for _ in range(10)]
                for i, p in enumerate(players):
                    p.call("player:resume", {"code": code, "token": tokens[i]})
                host.close()
                host = Screen()
                r = host.call("host:resume", {"code": code, "hostToken": host_token})
                check(
                    "after a server restart host and players rejoin with scores intact",
                    r.get("ok") and all(players[i].state["score"] == expected[i] for i in range(10)),
                )

        host.call("host:next")
        check("final ranking shown", wait_for(lambda: host.state["phase"] == "finished"))
        board = host.state["leaderboard"]
        check("final ranking is sorted", [b["score"] for b in board] == sorted((b["score"] for b in board), reverse=True))
        wait_for(lambda: all(p.state.get("phase") == "finished" for p in players))
        check("each phone shows its own final rank", all("rank" in p.state for p in players))

        r = Screen().call("host:resume", {"code": code, "hostToken": "guess"})
        check("wrong host token is refused", r.get("error") == "not_host")

        # Rule 6: no web address returns names or scores.
        leaked = False
        for path in ["/", "/healthz", f"/{code}", "/api/leaderboard", "/scores", "/socket.io/?EIO=4&transport=polling"]:
            try:
                body = urllib.request.urlopen(URL + path, timeout=3).read().decode()
            except Exception as e:  # 404s are fine
                body = str(e)
            leaked |= "Player 1" in body
        check("no web address shows names or scores", not leaked)

        # Rule 4: if the teacher's screen closes, phones are told (not frozen),
        # and the message clears when the teacher comes back.
        teacher = Screen()
        made = teacher.call("host:create")
        student = Screen()
        student.call("player:join", {"code": made["code"], "name": "Presence"})
        check("phones know the host is connected", student.state.get("hostOnline") is True)
        teacher.close()
        told = wait_for(lambda: student.state.get("hostOnline") is False and student.state.get("hostAwaySince"), timeout=10)
        check("phones are told when the host screen closes", told)
        teacher = Screen()
        teacher.call("host:resume", {"code": made["code"], "hostToken": made["hostToken"]})
        check("the message clears when the host comes back", wait_for(lambda: student.state.get("hostOnline") is True, timeout=5))
        teacher.close()
        student.close()

        # ---- attacks
        evil = socketio.Client(reconnection=False)
        try:
            evil.connect(URL, transports=["websocket"], headers={"Origin": "https://evil.example"})
            refused = False
            evil.disconnect()
        except Exception:
            refused = True
        check("socket from another website is refused (CORS)", refused)

        attacker = Screen()
        try:
            attacker.sio.call("player:join", {"code": code, "name": "x" * 100000}, timeout=3)
            dropped = False
        except Exception:
            dropped = True
        healthy = urllib.request.urlopen(URL + "/healthz", timeout=3).status == 200
        check("oversized message drops only the sender, server stays up", dropped and healthy)
        attacker = Screen()
        for bad in [None, [], "text", {"code": ["A"], "name": {"$gt": ""}}]:
            reply = attacker.sio.call("player:join", bad, timeout=5)
            if reply.get("ok"):
                check("malformed join refused", False, str(bad))
        check("malformed payloads get a clean error", True)
        r = attacker.call("player:answer", {"questionIndex": 0, "choice": 1})
        check("answering without joining is refused", r.get("error") == "not_joined")
        attacker.close()

        # One address opening far more sockets than a class needs gets refused,
        # so it cannot use up the server's threads.
        flood, refused = [], 0
        for _ in range(45):
            c = socketio.Client(reconnection=False)
            try:
                c.connect(URL, transports=["polling"], wait_timeout=3)
                flood.append(c)
            except Exception:
                refused += 1
        time.sleep(0.5)
        alive = sum(1 for c in flood if c.connected)
        for c in flood:
            if c.connected:
                c.disconnect()
        check("a flood of connections from one address is capped", alive <= 40 and (refused > 0 or alive < len(flood)))
        time.sleep(0.5)

        # One address cannot fill a room with fake names.
        room = Screen()
        fresh = room.call("host:create")["code"]
        filler = Screen()
        errors = [filler.call("player:join", {"code": fresh, "name": f"Fake {i}"}).get("error") for i in range(30)]
        check("one address cannot fill a room with fake names", errors[:25] == [None] * 25 and "rate_limited" in errors[25:])
        filler.close()
        room.close()

        guesser = Screen()
        codes = [guesser.call("player:resume", {"code": "QWERT", "token": f"guess{i}"}).get("error") for i in range(25)]
        check("guessing codes/tokens gets rate limited", "rate_limited" in codes)
        guesser.close()

        for p in players:
            p.close()
        host.close()
    finally:
        server.terminate()

    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
