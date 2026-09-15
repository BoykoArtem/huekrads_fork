import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace

import pytest


def make_user(user_id=1, username="alice", first_name="Alice"):
    return SimpleNamespace(id=user_id, username=username, first_name=first_name, is_bot=False)


def test_settings_default_and_roundtrip(temp_database):
    import database as db

    assert db.is_forward_reply_enabled(-1) is True
    assert db.is_auto_delete_enabled(-1) is True
    assert db.is_boss_enabled(-1) is True
    db.set_forward_reply_enabled(-1, False)
    db.set_auto_delete_enabled(-1, False)
    db.set_boss_enabled(-1, False)
    assert not db.is_forward_reply_enabled(-1)
    assert not db.is_auto_delete_enabled(-1)
    assert not db.is_boss_enabled(-1)


def test_user_is_created_for_game_and_duel(temp_database):
    import database as db

    db.save_or_update_user(make_user(), -100)
    duel = db.get_or_create_duel_user(make_user(), -100)
    assert duel["user_id"] == 1
    assert duel["points"] == 20
    assert db.get_duel_user_by_username("@alice", -100)["display_name"] == "alice"


def test_duel_transaction_preserves_current_scoring_rules(temp_database):
    import database as db

    winner = db.get_or_create_duel_user(make_user(1, "winner"), -100)
    loser = db.get_or_create_duel_user(make_user(2, "loser"), -100)
    winner_points, loser_points = db.execute_duel_transaction(-100, winner, loser, True)
    assert (winner_points, loser_points) == (30, 15)
    refreshed_winner = db.get_duel_user_by_username("winner", -100)
    refreshed_loser = db.get_duel_user_by_username("loser", -100)
    assert refreshed_winner["wins"] == 1
    assert refreshed_winner["daily_wins"] == 1
    assert refreshed_winner["stolen_dicks_count"] == 1
    assert refreshed_loser["losses"] == 1
    assert refreshed_loser["dick_stolen_today"] is True


@pytest.mark.parametrize("failing_update", [1, 2])
def test_duel_transaction_rolls_back_both_users_on_update_error(
    temp_database,
    monkeypatch,
    failing_update,
):
    import database as db

    chat_id = -101
    winner = db.get_or_create_duel_user(make_user(11, "rollback_winner"), chat_id)
    loser = db.get_or_create_duel_user(make_user(12, "rollback_loser"), chat_id)
    with sqlite3.connect(temp_database) as connection:
        connection.execute(
            """
            UPDATE duel_users
            SET points = 70, wins = 8, losses = 2, daily_wins = 4,
                stolen_dicks_count = 3, dick_stolen_count = 1,
                dick_stolen_today = 1, last_stolen_by = 'winner_history'
            WHERE user_id = ? AND chat_id = ?
            """,
            (winner["user_id"], chat_id),
        )
        connection.execute(
            """
            UPDATE duel_users
            SET points = 35, wins = 5, losses = 6, daily_wins = 2,
                stolen_dicks_count = 2, dick_stolen_count = 7,
                dick_stolen_today = 1, last_stolen_by = 'loser_history'
            WHERE user_id = ? AND chat_id = ?
            """,
            (loser["user_id"], chat_id),
        )

    winner_before = db.get_duel_user_by_username("rollback_winner", chat_id)
    loser_before = db.get_duel_user_by_username("rollback_loser", chat_id)
    real_get_db = db.get_db
    update_count = 0

    class FailingCursor:
        def __init__(self, cursor):
            self._cursor = cursor

        def execute(self, statement, parameters=()):
            nonlocal update_count
            if statement.lstrip().upper().startswith("UPDATE"):
                update_count += 1
                if update_count == failing_update:
                    raise sqlite3.OperationalError("injected UPDATE failure")
            return self._cursor.execute(statement, parameters)

        def __getattr__(self, name):
            return getattr(self._cursor, name)

    class ConnectionProxy:
        def __init__(self, connection):
            self._connection = connection

        def cursor(self):
            return FailingCursor(self._connection.cursor())

    @contextmanager
    def failing_get_db():
        with real_get_db() as connection:
            yield ConnectionProxy(connection)

    monkeypatch.setattr(db, "get_db", failing_get_db)

    with pytest.raises(sqlite3.OperationalError, match="injected UPDATE failure"):
        db.execute_duel_transaction(
            chat_id,
            winner_before,
            loser_before,
            is_dick_stolen=True,
        )

    assert update_count == failing_update
    monkeypatch.setattr(db, "get_db", real_get_db)
    assert db.get_duel_user_by_username("rollback_winner", chat_id) == winner_before
    assert db.get_duel_user_by_username("rollback_loser", chat_id) == loser_before


def test_game_birthdays_candidates_meta_and_boss_reward(temp_database, monkeypatch):
    import database as db

    user = make_user(7, "bob", "Bob")
    db.save_or_update_user(user, -77)
    assert db.save_custom_birthdate(-77, "@bob", "01.02")
    assert db.get_user_birthdate_from_db(7, -77) == "01.02"
    monkeypatch.setattr(db.random, "choice", lambda values: values[0])
    assert db.pick_beauty_of_the_day(-77) == ("bob", 1)
    assert db.get_top_beauties(-77) == [("bob", 1)]
    assert db.save_pizda_candidate(-77, 10, 1)
    assert db.pick_pizda_candidates(-77, 2, 1) == [10]
    db.mark_pizda_candidate_used(-77, 10)
    assert db.get_pizda_candidate_chats(2) == []
    db.set_bot_meta("key", "value")
    assert db.get_bot_meta("key") == "value"
    assert db.reward_boss_victory(7, -77)
    assert db.get_bosses_defeated(7, -77) == 1
    assert db.get_duel_user_by_username("bob", -77)["points"] == 100


def test_public_formatting_and_chance_contracts():
    import database as db

    assert db.format_user_title({"username": "@name", "display_name": "Other"}) == "name"
    assert db.format_user_title({"username": None, "display_name": "Other"}) == "Other"
    assert db.get_dick_steal_percent(0) == 20
    assert db.get_dick_steal_percent(3) == 23
    assert db.get_dick_steal_chance(3) == 0.23
