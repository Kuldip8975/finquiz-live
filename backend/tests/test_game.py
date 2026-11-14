"""Unit tests for the game rules in game.py (no network)."""

import json
import time

import pytest
from sqlalchemy import func, select

import config
import game
from db import Game, Session, init_db
from questions import QUESTIONS

init_db()


def new_room(players=("Asha", "Ben")):
    code, host_token = game.create_game()
    ids = [game.join_game(code, name)[0] for name in players]
    return code, host_token, ids


def open_question(code):
    return game.advance(code)


# ------------------------------------------------------------------ rooms


def test_room_code_format():
    code, token, _ = new_room()
    assert game.CODE_PATTERN.match(code)
    assert len(token) >= 40


def test_codes_are_case_insensitive_and_validated():
    code, _, _ = new_room()
    assert game.join_game(f"  {code.lower()} ", "Chandra")[2] == code
    with pytest.raises(game.GameError) as e:
        game.join_game("abc", "X")
    assert e.value.code == "room_not_found"
    with pytest.raises(game.GameError):
        game.join_game({"$ne": None}, "X")


def test_host_token_is_checked():
    code, token, _ = new_room()
    assert game.check_host(code, token) == code
    for bad in ["", "wrong", None, 123, "a" * 5000]:
        with pytest.raises(game.GameError) as e:
            game.check_host(code, bad)
        assert e.value.code == "not_host"


def test_tokens_are_stored_hashed():
    code, token, _ = new_room()
    with Session() as s:
        assert s.get(Game, code).host_token_hash != token


# ------------------------------------------------------------------ names


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  Asha   Rao ", "Asha Rao"),
        ("Ben​", "Ben"),  # zero-width space removed
        ("Eve‮", "Eve"),  # right-to-left override removed
        ("x" * 50, "x" * config.MAX_NAME_LENGTH),
        ("<b>Sam</b>", "<b>Sam</b>"),  # kept as text; React escapes it on screen
    ],
)
def test_names_are_cleaned(raw, expected):
    assert game.clean_name(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "​​", None])
def test_blank_names_are_refused(raw):
    with pytest.raises(game.GameError):
        game.clean_name(raw)


def test_duplicate_names_are_refused_ignoring_case():
    code, _, _ = new_room(["Asha"])
    with pytest.raises(game.GameError) as e:
        game.join_game(code, "ASHA")
    assert e.value.code == "name_taken"


def test_room_full(monkeypatch):
    monkeypatch.setattr(config, "MAX_PLAYERS_PER_GAME", 2)
    code, _, _ = new_room(["A", "B"])
    with pytest.raises(game.GameError) as e:
        game.join_game(code, "C")
    assert e.value.code == "room_full"


# ----------------------------------------------------------- flow & scoring


def test_cannot_start_without_players():
    code, _ = game.create_game()
    with pytest.raises(game.GameError) as e:
        game.advance(code)
    assert e.value.code == "no_players"


def test_correct_answer_scores_with_speed_bonus_and_wrong_scores_zero():
    code, _, (asha, ben) = new_room()
    open_question(code)
    right = QUESTIONS[0]["correct"]
    game.submit_answer(asha, 0, right)
    game.submit_answer(ben, 0, (right + 1) % 4)
    game.close_question(code, 0)
    views = game.room_views(code)[1]
    assert config.BASE_POINTS < views[asha]["score"] <= config.BASE_POINTS + config.SPEED_BONUS
    assert views[ben]["score"] == 0


def test_answer_only_once():
    code, _, (asha, _ben) = new_room()
    open_question(code)
    game.submit_answer(asha, 0, 0)
    with pytest.raises(game.GameError) as e:
        game.submit_answer(asha, 0, 1)
    assert e.value.code == "already_answered"


@pytest.mark.parametrize("choice", [-1, 4, "1", 1.0, True, None, [1]])
def test_bad_choices_are_refused(choice):
    code, _, (asha, _ben) = new_room()
    open_question(code)
    with pytest.raises(game.GameError) as e:
        game.submit_answer(asha, 0, choice)
    assert e.value.code == "bad_choice"


def test_answer_for_wrong_question_is_refused():
    code, _, (asha, _ben) = new_room()
    open_question(code)
    for index in [1, -1, "0", None]:
        with pytest.raises(game.GameError) as e:
            game.submit_answer(asha, index, 0)
        assert e.value.code == "closed"


def test_late_answer_is_refused():
    code, _, (asha, _ben) = new_room()
    open_question(code)
    with Session.begin() as s:
        g = s.get(Game, code)
        g.question_ends_at = time.time() - config.ANSWER_GRACE_SECONDS - 1
    with pytest.raises(game.GameError) as e:
        game.submit_answer(asha, 0, 0)
    assert e.value.code == "closed"


def test_everyone_answered_is_reported():
    code, _, (asha, ben) = new_room()
    open_question(code)
    assert game.submit_answer(asha, 0, 0) is False
    assert game.submit_answer(ben, 0, 0) is True


def test_close_question_is_idempotent():
    code, _, _ = new_room()
    open_question(code)
    assert game.close_question(code, 0) is True
    assert game.close_question(code, 0) is False


def test_cannot_skip_an_open_question():
    code, _, _ = new_room()
    open_question(code)
    with pytest.raises(game.GameError) as e:
        game.advance(code)
    assert e.value.code == "question_open"


def test_full_game_reaches_finished_and_ties_share_rank():
    code, _, (asha, ben) = new_room()
    for i in range(len(QUESTIONS)):
        open_question(code)
        game.close_question(code, i)  # nobody answers: everyone on 0
    assert game.advance(code)["phase"] == "finished"
    host, players = game.room_views(code)
    assert [r["rank"] for r in host["leaderboard"]] == [1, 1]
    assert players[asha]["rank"] == players[ben]["rank"] == 1
    with pytest.raises(game.GameError):
        game.join_game(code, "Late")


# ------------------------------------------------------ what screens may see


def test_open_question_views_never_contain_the_answer():
    code, _, (asha, ben) = new_room()
    open_question(code)
    game.submit_answer(asha, 0, QUESTIONS[0]["correct"])
    host, players = game.room_views(code)
    for view in [host, *players.values()]:
        raw = json.dumps(view)
        assert "correctIndex" not in raw
        assert QUESTIONS[0]["explanation"] not in raw
        assert "score" not in view["question"]
    # The player who answered must not learn from their score either.
    assert "score" not in players[asha] and "wasCorrect" not in players[asha]


def test_player_views_never_contain_other_players():
    code, _, (asha, ben) = new_room(["Asha", "Ben"])
    open_question(code)
    game.close_question(code, 0)
    _, players = game.room_views(code)
    assert "Ben" not in json.dumps(players[asha])
    assert "Asha" not in json.dumps(players[ben])
    assert "leaderboard" not in players[asha]


def test_reveal_shows_answer_to_everyone():
    code, _, (asha, _ben) = new_room()
    open_question(code)
    game.close_question(code, 0)
    host, players = game.room_views(code)
    assert host["question"]["correctIndex"] == QUESTIONS[0]["correct"]
    assert players[asha]["question"]["correctIndex"] == QUESTIONS[0]["correct"]
    assert len(host["leaderboard"]) == 2


def test_resume_finds_the_same_player():
    code, _ = game.create_game()
    pid, token, _ = game.join_game(code, "Asha")
    assert game.find_player(code, token) == (pid, code)
    for bad in ["", "nope", None, "a" * 500]:
        with pytest.raises(game.GameError):
            game.find_player(code, bad)
    other, _ = game.create_game()
    with pytest.raises(game.GameError):
        game.find_player(other, token)  # a token only works in its own room


# ----------------------------------------------------------------- cleanup


def test_old_games_are_deleted(monkeypatch):
    code, _, _ = new_room()
    with Session.begin() as s:
        s.get(Game, code).created_at = time.time() - (config.GAME_TTL_HOURS + 1) * 3600
    assert game.delete_old_games() >= 1
    with pytest.raises(game.GameError):
        game.host_view(code)


def test_room_creation_is_capped(monkeypatch):
    with Session() as s:
        current = s.scalar(select(func.count()).select_from(Game))
    monkeypatch.setattr(config, "MAX_ACTIVE_GAMES", current)
    with pytest.raises(game.GameError) as e:
        game.create_game()
    assert e.value.code == "busy"


# --------------------------------------------------------- name spoofing


@pytest.mark.parametrize(
    "raw",
    [
        "Аsha",  # Cyrillic A + Latin "sha"
        "Ashа",  # Latin + Cyrillic a
        "Bεn",  # Greek epsilon inside a Latin name
    ],
)
def test_mixed_latin_and_lookalike_scripts_are_refused(raw):
    with pytest.raises(game.GameError) as e:
        game.clean_name(raw)
    assert e.value.code == "bad_name"


@pytest.mark.parametrize("raw", ["आशा", "Аша", "Asha Rao", "José"])
def test_single_script_names_are_allowed(raw):
    assert game.clean_name(raw)


def test_fullwidth_letters_become_plain():
    assert game.clean_name("Ａｓｈａ") == "Asha"


@pytest.mark.parametrize(
    "lookalike",
    [
        "ASHA",
        "Ásha",  # accented
        "As ha",  # extra space
        "Аѕһа",  # all-Cyrillic look-alike of "Asha"
        "Ａｓｈａ",  # full-width
    ],
)
def test_lookalike_names_count_as_duplicates(lookalike):
    code, _, _ = new_room(["Asha"])
    with pytest.raises(game.GameError) as e:
        game.join_game(code, lookalike)
    assert e.value.code == "name_taken"
