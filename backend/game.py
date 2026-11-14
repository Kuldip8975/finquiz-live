"""Game rules. No networking here: server.py calls these functions and sends
the results over Socket.IO.

The view functions at the bottom decide what each screen is allowed to see.
That is where rule 1 (answers stay on the server) and rule 6 (scores are not
public) are enforced.
"""

import hashlib
import re
import secrets
import threading
import time
import unicodedata

from sqlalchemy import delete, func, select

import config
from db import Answer, Game, Player, Session
from questions import QUESTIONS

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ"  # no I, L or O: easy to read off a projector
CODE_LENGTH = 5
CODE_PATTERN = re.compile(rf"^[{CODE_ALPHABET}]{{{CODE_LENGTH}}}$")
MAX_TOKEN_LENGTH = 64

# One lock for every change to game state. Ten (or sixty) players answering in
# the same second are handled one at a time, so scores can never be counted twice.
lock = threading.RLock()


class GameError(Exception):
    """An expected problem we show to the user, e.g. a wrong room code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


ROOM_NOT_FOUND = ("room_not_found", "Room not found. Check the code on the projector.")


# ------------------------------------------------------------ input cleaning


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def clean_code(code) -> str:
    """Upper-case and validate a room code. Anything malformed is 'not found'."""
    code = str(code or "").strip().upper()
    if not CODE_PATTERN.match(code):
        raise GameError(*ROOM_NOT_FOUND)
    return code


def clean_token(token) -> str:
    if not isinstance(token, str) or not 0 < len(token) <= MAX_TOKEN_LENGTH:
        return ""
    return token


def clean_name(name) -> str:
    """Tidy a player's name so it cannot be blank-looking or pretend to be
    someone else on the projector:
      - NFKC turns look-alike forms (full-width "Ａｓｈａ", ligatures) into plain letters
      - invisible/control characters (zero-width spaces, direction overrides) are dropped
      - Latin mixed with Cyrillic or Greek is refused ("Аsha" with a Cyrillic А)
    Names written fully in one script (Devanagari, Cyrillic, ...) are fine."""
    text = unicodedata.normalize("NFKC", str(name or "")[:200])
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")
    text = " ".join(text.split())[: config.MAX_NAME_LENGTH]
    if not text:
        raise GameError("bad_name", "Please type your name.")
    scripts = {unicodedata.name(ch, "?").split(" ")[0] for ch in text if ch.isalpha()}
    if "LATIN" in scripts and scripts & MIXABLE_SCRIPTS:
        raise GameError("bad_name", "Please write your name using one alphabet.")
    return text


# Scripts with letters that look exactly like Latin ones.
MIXABLE_SCRIPTS = {"CYRILLIC", "GREEK", "ARMENIAN", "CHEROKEE", "COPTIC"}

# Cyrillic and Greek letters that look like Latin letters, for duplicate checks.
_LOOKALIKES = str.maketrans(
    # Cyrillic lower | Cyrillic upper | Greek lower | Greek upper  (spaces map to spaces)
    "аеорсухіјѕԁԛԝӏһбвнкмт АВЕЅІЈКМНОРСТХУ αβεικνορτυχ ΑΒΕΖΗΙΚΜΝΟΡΤΥΧ",
    "aeopcyxijsdqwlhbbhkmt abesijkmhopctxy abeikvoptux abezhikmnoptyx",
)


def name_key(name: str) -> str:
    """What a name *looks like*, for spotting duplicates: lower case, no
    accents or spaces, look-alike letters mapped to Latin. "Asha", "ASHA",
    "Ásha" and "As ha" all give the same key."""
    text = unicodedata.normalize("NFKD", name.casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch) and not ch.isspace())
    return text.translate(_LOOKALIKES)


def _now() -> float:
    return time.time()


def _ms(t: float | None) -> int | None:
    return None if t is None else int(t * 1000)


def _get_game(s, code) -> Game:
    game = s.get(Game, clean_code(code))
    if game is None:
        raise GameError(*ROOM_NOT_FOUND)
    return game


# ---------------------------------------------------------------- host actions


def create_game() -> tuple[str, str]:
    """Make a new room. Returns (room code, secret host token)."""
    with lock, Session.begin() as s:
        if s.scalar(select(func.count()).select_from(Game)) >= config.MAX_ACTIVE_GAMES:
            raise GameError("busy", "The server is busy. Please try again in a few minutes.")
        for _ in range(50):
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if s.get(Game, code) is None:
                break
        else:
            raise GameError("busy", "Could not create a room. Please try again.")
        token = secrets.token_urlsafe(32)
        s.add(Game(code=code, host_token_hash=_hash(token), phase="lobby", question_index=-1, created_at=_now()))
    return code, token


def check_host(code, token) -> str:
    """Raise unless `token` is the host token for this room. Returns the clean code."""
    with Session() as s:
        game = _get_game(s, code)
        if not secrets.compare_digest(game.host_token_hash, _hash(clean_token(token))):
            raise GameError("not_host", "This screen is not the host of that room.")
        return game.code


def advance(code) -> dict:
    """Host pressed Start / Next. Opens the next question, or finishes the quiz.

    Returns {"phase", "question_index", "ends_at"} so the server can start the
    countdown timer.
    """
    with lock, Session.begin() as s:
        game = _get_game(s, code)
        if game.phase == "question":
            raise GameError("question_open", "Wait for this question to close first.")
        if game.phase == "finished":
            raise GameError("finished", "The quiz has already finished.")
        if game.phase == "lobby":
            players = s.scalar(select(func.count()).where(Player.game_code == game.code))
            if players == 0:
                raise GameError("no_players", "Wait for at least one player to join.")

        next_index = game.question_index + 1
        if next_index >= len(QUESTIONS):
            game.phase = "finished"
            game.question_started_at = game.question_ends_at = None
        else:
            now = _now()
            game.phase = "question"
            game.question_index = next_index
            game.question_started_at = now
            game.question_ends_at = now + config.QUESTION_SECONDS
        return {"phase": game.phase, "question_index": game.question_index, "ends_at": game.question_ends_at}


def close_question(code: str, question_index: int) -> bool:
    """Close the question if it is still open. Returns True if it closed now.

    Called by the timer, and early when every player has answered. Safe to
    call twice: the second call does nothing.
    """
    with lock, Session.begin() as s:
        game = s.get(Game, code)
        if game and game.phase == "question" and game.question_index == question_index:
            game.phase = "reveal"
            return True
        return False


def open_questions() -> list[tuple[str, int, float]]:
    """Questions that were running when the server last stopped, so their
    timers can be restarted on boot."""
    with Session() as s:
        rows = s.execute(select(Game.code, Game.question_index, Game.question_ends_at).where(Game.phase == "question")).all()
        return [(r[0], r[1], r[2]) for r in rows]


def delete_old_games() -> int:
    """Remove games older than GAME_TTL_HOURS, with their players and answers."""
    cutoff = _now() - config.GAME_TTL_HOURS * 3600
    with lock, Session.begin() as s:
        codes = list(s.scalars(select(Game.code).where(Game.created_at < cutoff)))
        if codes:
            s.execute(delete(Answer).where(Answer.game_code.in_(codes)))
            s.execute(delete(Player).where(Player.game_code.in_(codes)))
            s.execute(delete(Game).where(Game.code.in_(codes)))
        return len(codes)


# -------------------------------------------------------------- player actions


def join_game(code, name) -> tuple[int, str, str]:
    """Add a player. Returns (player id, secret player token, room code)."""
    name = clean_name(name)
    with lock, Session.begin() as s:
        game = _get_game(s, code)
        if game.phase == "finished":
            raise GameError("finished", "This quiz has already finished.")
        count = s.scalar(select(func.count()).where(Player.game_code == game.code))
        if count >= config.MAX_PLAYERS_PER_GAME:
            raise GameError("room_full", "This room is full.")
        taken = s.scalar(select(Player.id).where(Player.game_code == game.code, Player.name_key == name_key(name)[:40]))
        if taken:
            raise GameError("name_taken", "Someone in this room already has that name. Try another.")

        token = secrets.token_urlsafe(32)
        player = Player(
            game_code=game.code, name=name, name_key=name_key(name)[:40], token_hash=_hash(token), score=0, joined_at=_now()
        )
        s.add(player)
        s.flush()
        return player.id, token, game.code


def find_player(code, token) -> tuple[int, str]:
    """Look a player up by their saved token (used after a refresh or a dropped
    connection). Returns (player id, room code)."""
    code = clean_code(code)
    token = clean_token(token)
    with Session() as s:
        player = s.scalar(select(Player).where(Player.token_hash == _hash(token))) if token else None
        if player is None or player.game_code != code:
            raise GameError("player_not_found", "We could not find you in that room. Please join again.")
        return player.id, player.game_code


def submit_answer(player_id: int, question_index, choice) -> bool:
    """Record an answer. Returns True if every player has now answered."""
    # bool is a subclass of int in Python, so rule it out explicitly.
    if type(choice) is not int or not 0 <= choice < 4:
        raise GameError("bad_choice", "That is not a valid option.")
    if type(question_index) is not int:
        raise GameError("closed", "Time is up for this question.")

    with lock, Session.begin() as s:
        player = s.get(Player, player_id)
        game = s.get(Game, player.game_code)
        now = _now()
        if (
            game.phase != "question"
            or game.question_index != question_index
            or now > game.question_ends_at + config.ANSWER_GRACE_SECONDS
        ):
            raise GameError("closed", "Time is up for this question.")
        already = s.scalar(select(Answer.id).where(Answer.player_id == player.id, Answer.question_index == question_index))
        if already:
            raise GameError("already_answered", "You have already answered this question.")

        correct = choice == QUESTIONS[question_index]["correct"]
        points = 0
        if correct:
            duration = game.question_ends_at - game.question_started_at
            remaining = max(0.0, game.question_ends_at - now)
            points = config.BASE_POINTS + round(config.SPEED_BONUS * min(1.0, remaining / duration))

        s.add(
            Answer(
                player_id=player.id,
                game_code=game.code,
                question_index=question_index,
                choice=choice,
                is_correct=correct,
                points=points,
                answered_at=now,
            )
        )
        player.score += points
        s.flush()

        players = s.scalar(select(func.count()).where(Player.game_code == game.code))
        answered = s.scalar(select(func.count()).where(Answer.game_code == game.code, Answer.question_index == question_index))
        return answered >= players


# ----------------------------------------------------------------------- views
#
# A "snapshot" reads everything a room needs in three queries (game, players,
# answers to the current question). All views are then built from it in
# memory, so updating a room of 60 players costs the same few queries as
# updating one.


def _public_question(index: int) -> dict:
    """A question as it may be shown while it is open: no answer."""
    q = QUESTIONS[index]
    return {"index": index, "text": q["text"], "options": list(q["options"])}


def _revealed_question(index: int) -> dict:
    q = QUESTIONS[index]
    return {**_public_question(index), "correctIndex": q["correct"], "explanation": q["explanation"], "source": q["source"]}


class _Snapshot:
    def __init__(self, s, game: Game):
        self.game = game
        players = s.scalars(
            select(Player).where(Player.game_code == game.code).order_by(Player.score.desc(), Player.joined_at, Player.id)
        ).all()
        # Equal scores share a rank (1, 2, 2, 4).
        self.ranking: list[dict] = []
        last_score, last_rank = None, 0
        for position, p in enumerate(players, start=1):
            rank = last_rank if p.score == last_score else position
            self.ranking.append({"id": p.id, "name": p.name, "score": p.score, "rank": rank, "joined_at": p.joined_at})
            last_score, last_rank = p.score, rank
        self.by_id = {r["id"]: r for r in self.ranking}

        self.answers: dict[int, Answer] = {}
        if game.question_index >= 0:
            for a in s.scalars(select(Answer).where(Answer.game_code == game.code, Answer.question_index == game.question_index)):
                self.answers[a.player_id] = a

    def base(self) -> dict:
        g = self.game
        return {
            "code": g.code,
            "phase": g.phase,
            "questionIndex": g.question_index,
            "totalQuestions": len(QUESTIONS),
            "playerCount": len(self.ranking),
            "serverNow": _ms(_now()),
        }

    def leaderboard(self) -> list[dict]:
        return [{"name": r["name"], "score": r["score"], "rank": r["rank"]} for r in self.ranking]

    def host_view(self) -> dict:
        """What the projector shows. Only sent to a socket that proved it holds
        the host token."""
        g = self.game
        view = {**self.base(), "role": "host"}

        if g.phase == "lobby":
            view["players"] = [r["name"] for r in sorted(self.ranking, key=lambda r: r["joined_at"])]

        elif g.phase == "question":
            # The projector is visible to the whole class, so the answer is
            # held back here too until the question closes.
            view["question"] = _public_question(g.question_index)
            view["endsAt"] = _ms(g.question_ends_at)
            view["startedAt"] = _ms(g.question_started_at)
            view["answeredCount"] = len(self.answers)

        elif g.phase == "reveal":
            counts = [0, 0, 0, 0]
            for a in self.answers.values():
                counts[a.choice] += 1
            view["question"] = _revealed_question(g.question_index)
            view["answerCounts"] = counts
            view["leaderboard"] = self.leaderboard()
            view["isLastQuestion"] = g.question_index == len(QUESTIONS) - 1

        elif g.phase == "finished":
            view["leaderboard"] = self.leaderboard()

        return view

    def player_view(self, player_id: int) -> dict:
        """What one player's phone shows. Never contains other players' names
        or scores, and never contains the correct answer while a question is
        open."""
        g = self.game
        me = self.by_id[player_id]
        mine = self.answers.get(player_id)
        view = {**self.base(), "role": "player", "name": me["name"]}

        if g.phase == "question":
            view["question"] = _public_question(g.question_index)
            view["endsAt"] = _ms(g.question_ends_at)
            view["startedAt"] = _ms(g.question_started_at)
            view["myChoice"] = mine.choice if mine else None
            # No score here: a score that jumps right after answering would
            # tell the player whether they were right before the reveal.

        elif g.phase in ("reveal", "finished"):
            view["score"] = me["score"]
            view["rank"] = me["rank"]
            if g.phase == "reveal":
                view["question"] = _revealed_question(g.question_index)
                view["myChoice"] = mine.choice if mine else None
                view["wasCorrect"] = bool(mine and mine.is_correct)
                view["pointsGained"] = mine.points if mine else 0

        return view


def host_view(code) -> dict:
    with Session() as s:
        return _Snapshot(s, _get_game(s, code)).host_view()


def player_view(player_id: int) -> dict:
    with Session() as s:
        player = s.get(Player, player_id)
        return _Snapshot(s, s.get(Game, player.game_code)).player_view(player_id)


def room_views(code) -> tuple[dict, dict[int, dict]]:
    """The host view and every player's view, from one snapshot."""
    with Session() as s:
        snap = _Snapshot(s, _get_game(s, code))
        return snap.host_view(), {pid: snap.player_view(pid) for pid in snap.by_id}
