from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_run_game_sends_existing_two_message_sequence(monkeypatch, fake_context):
    from handlers import game

    monkeypatch.setattr(game, "pick_beauty_of_the_day", lambda chat_id: ("alice", 2))
    monkeypatch.setattr(game.asyncio, "sleep", AsyncMock())
    await game.run_pidor_game_in_chat(fake_context, -1)
    assert fake_context.bot.send_message.await_count == 2
    assert "Выбираем" in fake_context.bot.send_message.await_args_list[0].kwargs["text"]


@pytest.mark.asyncio
async def test_daily_game_continues_after_chat_error(monkeypatch, fake_context):
    from handlers import game

    calls = []
    monkeypatch.setattr(game, "get_all_chats", lambda: [-1, -2])

    async def run(_context, chat_id):
        calls.append(chat_id)
        if chat_id == -1:
            raise RuntimeError("expected test failure")

    monkeypatch.setattr(game, "run_pidor_game_in_chat", run)
    await game.daily_beauty_job(fake_context)
    assert calls == [-1, -2]
