from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def test_hyperborean_public_reexports():
    from handlers import duel, hyperborean_event

    assert duel.hyperboreic_huy_daily_job is hyperborean_event.hyperboreic_huy_daily_job
    assert duel.hyperboreic_huy_callback is hyperborean_event.hyperboreic_huy_callback
    assert duel.ACTIVE_HYPERBOREAN_EVENTS is hyperborean_event.ACTIVE_HYPERBOREAN_EVENTS


@pytest.mark.parametrize("event_type", ["hyperboreic", "arthur"])
async def test_spawn_respects_state_chance_and_event_type(monkeypatch, fake_context, event_type):
    from handlers import hyperborean_event as event

    event.ACTIVE_HYPERBOREAN_EVENTS.clear()
    event.ACTIVE_HYPERBOREAN_EVENTS[-1] = {"message_id": 1, "event_type": event_type}
    await event._spawn_hyperboreic_huy(fake_context, -1)
    fake_context.bot.send_message.assert_not_awaited()

    event.ACTIVE_HYPERBOREAN_EVENTS.clear()
    monkeypatch.setattr(event.random, "random", lambda: 1.0)
    await event._spawn_hyperboreic_huy(fake_context, -1)
    fake_context.bot.send_message.assert_not_awaited()

    monkeypatch.setattr(event.random, "random", lambda: 0.0)
    monkeypatch.setattr(event.random, "choice", lambda values: event_type)
    await event._spawn_hyperboreic_huy(fake_context, -1)
    assert event.ACTIVE_HYPERBOREAN_EVENTS[-1] == {"message_id": 101, "event_type": event_type}
    assert fake_context.bot.send_message.await_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "hyperboreic_huy"


def test_claim_uses_temporary_database(monkeypatch, temp_database, tg_user):
    from handlers import hyperborean_event as event

    monkeypatch.setattr(event, "_HYPERBOREAN_DB_PATH", temp_database)
    assert event._claim_hyperboreic_huy(-99, tg_user) == "exploded"
    assert event._claim_hyperboreic_huy(-99, tg_user) == "restored"


async def test_callback_restores_event_state_after_claim_error(monkeypatch, fake_context, tg_user):
    from handlers import hyperborean_event as event

    event.ACTIVE_HYPERBOREAN_EVENTS.clear()
    saved = {"message_id": 77, "event_type": "hyperboreic"}
    event.ACTIVE_HYPERBOREAN_EVENTS[-1] = saved
    monkeypatch.setattr(event, "_claim_hyperboreic_huy", lambda *_args: "error")
    query = SimpleNamespace(data="hyperboreic_huy", from_user=tg_user, answer=AsyncMock())
    update = SimpleNamespace(callback_query=query, effective_chat=SimpleNamespace(id=-1))

    await event.hyperboreic_huy_callback(update, fake_context)

    assert event.ACTIVE_HYPERBOREAN_EVENTS[-1] == saved
