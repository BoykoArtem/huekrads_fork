import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


CHAT_ID = -4343


def make_user(user_id, username):
    return SimpleNamespace(
        id=user_id,
        username=username,
        first_name=username.title(),
        last_name=None,
        is_bot=False,
    )


def set_duel_stats(
    database_path,
    user_id,
    *,
    points,
    wins,
    losses,
    daily_wins,
    stolen_dicks_count,
    dick_stolen_count,
    dick_stolen_today,
    last_stolen_by,
):
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE duel_users
            SET points = ?, wins = ?, losses = ?, daily_wins = ?,
                stolen_dicks_count = ?, dick_stolen_count = ?,
                dick_stolen_today = ?, last_stolen_by = ?
            WHERE user_id = ? AND chat_id = ?
            """,
            (
                points,
                wins,
                losses,
                daily_wins,
                stolen_dicks_count,
                dick_stolen_count,
                dick_stolen_today,
                last_stolen_by,
                user_id,
                CHAT_ID,
            ),
        )


@pytest.fixture(autouse=True)
def clean_active_duels():
    from handlers import duel

    duel.ACTIVE_DUELS.clear()
    yield
    duel.ACTIVE_DUELS.clear()


@pytest.fixture
def fixed_duel_database(monkeypatch, temp_database):
    import database

    monkeypatch.setattr(database, "_get_today_date_str", lambda: "2030-01-02")
    return temp_database


@pytest.mark.asyncio
async def test_finish_duel_no_steal_caps_points_and_completes_after_delete_error(
    monkeypatch,
    fixed_duel_database,
    fake_context,
):
    import database
    from handlers import duel

    winner_tg = make_user(101, "cap_winner")
    loser_tg = make_user(102, "floor_loser")
    database.get_or_create_duel_user(winner_tg, CHAT_ID)
    database.get_or_create_duel_user(loser_tg, CHAT_ID)
    set_duel_stats(
        fixed_duel_database,
        winner_tg.id,
        points=95,
        wins=4,
        losses=2,
        daily_wins=3,
        stolen_dicks_count=5,
        dick_stolen_count=1,
        dick_stolen_today=0,
        last_stolen_by="old_winner_thief",
    )
    set_duel_stats(
        fixed_duel_database,
        loser_tg.id,
        points=3,
        wins=2,
        losses=6,
        daily_wins=0,
        stolen_dicks_count=4,
        dick_stolen_count=7,
        dick_stolen_today=0,
        last_stolen_by="old_loser_thief",
    )
    winner = database.get_duel_user_by_username("cap_winner", CHAT_ID)
    loser = database.get_duel_user_by_username("floor_loser", CHAT_ID)
    duel.ACTIVE_DUELS[CHAT_ID] = {
        "round": 4,
        "message_id": 701,
        "original_msg_id": 702,
    }

    steal_roll = Mock(return_value=0.99)
    choices = []

    def choose(values):
        choices.append(values)
        return values[0]

    monkeypatch.setattr(duel.random, "random", steal_roll)
    monkeypatch.setattr(duel.random, "choice", choose)
    fake_context.bot.delete_message = AsyncMock(
        side_effect=RuntimeError("old duel message is already gone")
    )
    fake_context.bot.send_message = AsyncMock(
        return_value=SimpleNamespace(message_id=703)
    )
    fake_context.bot.send_animation = AsyncMock()

    await duel._finish_duel(
        fake_context,
        CHAT_ID,
        winner,
        loser,
        custom_text="Детерминированный финал.\n",
    )

    refreshed_winner = database.get_duel_user_by_username("cap_winner", CHAT_ID)
    refreshed_loser = database.get_duel_user_by_username("floor_loser", CHAT_ID)
    assert (
        refreshed_winner["points"],
        refreshed_winner["wins"],
        refreshed_winner["losses"],
        refreshed_winner["daily_wins"],
        refreshed_winner["stolen_dicks_count"],
        refreshed_winner["dick_stolen_count"],
        refreshed_winner["dick_stolen_today"],
        refreshed_winner["last_stolen_by"],
    ) == (100, 5, 2, 4, 5, 1, False, "old_winner_thief")
    assert (
        refreshed_loser["points"],
        refreshed_loser["wins"],
        refreshed_loser["losses"],
        refreshed_loser["daily_wins"],
        refreshed_loser["stolen_dicks_count"],
        refreshed_loser["dick_stolen_count"],
        refreshed_loser["dick_stolen_today"],
        refreshed_loser["last_stolen_by"],
    ) == (0, 2, 7, 0, 4, 7, False, "old_loser_thief")
    assert CHAT_ID not in duel.ACTIVE_DUELS
    steal_roll.assert_called_once_with()
    assert len(choices) == 1

    fake_context.bot.delete_message.assert_awaited_once_with(
        chat_id=CHAT_ID,
        message_id=701,
    )
    fake_context.bot.send_message.assert_awaited_once()
    final_call = fake_context.bot.send_message.await_args
    assert final_call.kwargs["chat_id"] == CHAT_ID
    assert final_call.kwargs["parse_mode"] == "HTML"
    assert "Детерминированный финал." in final_call.kwargs["text"]
    assert "🗡️ <b>Результаты дуэли:</b>" in final_call.kwargs["text"]
    assert "(100/100)" in final_call.kwargs["text"]
    assert "(0/100)" in final_call.kwargs["text"]
    assert fake_context.job_queue.calls == [
        (
            duel.delete_messages_job,
            duel.AUTO_DELETE_DELAY,
            {"data": {"chat_id": CHAT_ID, "message_ids": [703, 702]}},
        )
    ]
    fake_context.bot.send_animation.assert_awaited_once_with(
        chat_id=CHAT_ID,
        animation=duel.WINNER_100_PTS_GIF,
        caption="🏆 <b>cap_winner</b> набрал 100 очков!",
        parse_mode="HTML",
    )


@pytest.mark.asyncio
async def test_finish_duel_steal_keeps_final_message_and_schedules_original_only(
    monkeypatch,
    fixed_duel_database,
    fake_context,
):
    import database
    from handlers import duel

    winner_tg = make_user(201, "steal_winner")
    loser_tg = make_user(202, "steal_loser")
    database.get_or_create_duel_user(winner_tg, CHAT_ID)
    database.get_or_create_duel_user(loser_tg, CHAT_ID)
    set_duel_stats(
        fixed_duel_database,
        winner_tg.id,
        points=40,
        wins=2,
        losses=1,
        daily_wins=1,
        stolen_dicks_count=3,
        dick_stolen_count=0,
        dick_stolen_today=0,
        last_stolen_by=None,
    )
    set_duel_stats(
        fixed_duel_database,
        loser_tg.id,
        points=20,
        wins=5,
        losses=4,
        daily_wins=2,
        stolen_dicks_count=1,
        dick_stolen_count=6,
        dick_stolen_today=0,
        last_stolen_by=None,
    )
    winner = database.get_duel_user_by_username("steal_winner", CHAT_ID)
    loser = database.get_duel_user_by_username("steal_loser", CHAT_ID)
    duel.ACTIVE_DUELS[CHAT_ID] = {
        "round": 2,
        "message_id": 801,
        "original_msg_id": 802,
    }

    steal_roll = Mock(return_value=0.0)
    choices = []

    def choose(values):
        choices.append(values)
        return values[0]

    monkeypatch.setattr(duel.random, "random", steal_roll)
    monkeypatch.setattr(duel.random, "choice", choose)
    fake_context.bot.send_message = AsyncMock(
        return_value=SimpleNamespace(message_id=803)
    )
    fake_context.bot.send_animation = AsyncMock()

    await duel._finish_duel(
        fake_context,
        CHAT_ID,
        winner,
        loser,
        custom_text="Результат с кражей.\n",
    )

    refreshed_winner = database.get_duel_user_by_username("steal_winner", CHAT_ID)
    refreshed_loser = database.get_duel_user_by_username("steal_loser", CHAT_ID)
    assert (
        refreshed_winner["points"],
        refreshed_winner["wins"],
        refreshed_winner["losses"],
        refreshed_winner["daily_wins"],
        refreshed_winner["stolen_dicks_count"],
    ) == (50, 3, 1, 2, 4)
    assert (
        refreshed_loser["points"],
        refreshed_loser["wins"],
        refreshed_loser["losses"],
        refreshed_loser["daily_wins"],
        refreshed_loser["dick_stolen_count"],
        refreshed_loser["dick_stolen_today"],
        refreshed_loser["last_stolen_by"],
    ) == (15, 5, 5, 2, 7, True, "steal_winner")
    assert CHAT_ID not in duel.ACTIVE_DUELS
    steal_roll.assert_called_once_with()
    assert len(choices) == 2
    assert choices[1] is duel.DWARFS_FACTS

    fake_context.bot.delete_message.assert_awaited_once_with(
        chat_id=CHAT_ID,
        message_id=801,
    )
    fake_context.bot.send_message.assert_awaited_once()
    final_call = fake_context.bot.send_message.await_args
    assert final_call.kwargs["parse_mode"] == "HTML"
    assert "И ВДОБАВОК У НЕГО УКРАЛИ ХУЙ" in final_call.kwargs["text"]
    assert duel.DWARFS_FACTS[0] in final_call.kwargs["text"]
    assert fake_context.job_queue.calls == [
        (
            duel.delete_messages_job,
            duel.AUTO_DELETE_DELAY,
            {"data": {"chat_id": CHAT_ID, "message_ids": [802]}},
        )
    ]
    assert 803 not in fake_context.job_queue.calls[0][2]["data"]["message_ids"]
    fake_context.bot.send_animation.assert_not_awaited()


@pytest.mark.asyncio
async def test_finish_duel_transaction_error_clears_state_and_schedules_error(
    monkeypatch,
    fixed_duel_database,
    fake_context,
):
    import database
    from handlers import duel

    winner_tg = make_user(301, "error_winner")
    loser_tg = make_user(302, "error_loser")
    winner = database.get_or_create_duel_user(winner_tg, CHAT_ID)
    loser = database.get_or_create_duel_user(loser_tg, CHAT_ID)
    duel.ACTIVE_DUELS[CHAT_ID] = {
        "round": 3,
        "message_id": 901,
        "original_msg_id": 902,
    }

    steal_roll = Mock(return_value=0.99)
    presentation_choice = Mock(side_effect=AssertionError("presentation continued"))
    monkeypatch.setattr(duel.random, "random", steal_roll)
    monkeypatch.setattr(duel.random, "choice", presentation_choice)
    monkeypatch.setattr(
        duel,
        "execute_duel_transaction",
        Mock(side_effect=RuntimeError("database failed")),
    )
    fake_context.bot.send_message = AsyncMock(
        return_value=SimpleNamespace(message_id=903)
    )
    fake_context.bot.send_animation = AsyncMock()

    await duel._finish_duel(
        fake_context,
        CHAT_ID,
        winner,
        loser,
        custom_text="Этот финал не должен отправиться.\n",
    )

    assert CHAT_ID not in duel.ACTIVE_DUELS
    steal_roll.assert_called_once_with()
    presentation_choice.assert_not_called()
    fake_context.bot.send_message.assert_awaited_once_with(
        CHAT_ID,
        "⚠️ Ошибка проведения дуэли. Попробуйте снова.",
    )
    fake_context.bot.delete_message.assert_not_awaited()
    fake_context.bot.send_animation.assert_not_awaited()
    assert fake_context.job_queue.calls == [
        (
            duel.delete_messages_job,
            duel.AUTO_DELETE_DELAY,
            {"data": {"chat_id": CHAT_ID, "message_ids": [903]}},
        )
    ]
