from types import SimpleNamespace
from unittest.mock import AsyncMock


def test_schedule_auto_delete_uses_current_delay_and_skips_missing_queue(
    fake_context,
):
    from handlers import duel

    message_ids = [101, 102]
    duel.schedule_auto_delete(fake_context, -55, message_ids)

    assert duel.AUTO_DELETE_DELAY == 60
    assert fake_context.job_queue.calls == [
        (
            duel.delete_messages_job,
            60,
            {"data": {"chat_id": -55, "message_ids": message_ids}},
        )
    ]

    fake_context.job_queue = None
    duel.schedule_auto_delete(fake_context, -55, [103])


async def test_delete_messages_job_continues_after_delete_error():
    from handlers import duel

    deleted_ids = []

    async def delete_message(*, chat_id, message_id):
        deleted_ids.append((chat_id, message_id))
        if message_id == 2:
            raise RuntimeError("Telegram delete failed")

    context = SimpleNamespace(
        job=SimpleNamespace(data={"chat_id": -56, "message_ids": [1, 2, 3]}),
        bot=SimpleNamespace(delete_message=AsyncMock(side_effect=delete_message)),
    )

    await duel.delete_messages_job(context)

    assert deleted_ids == [(-56, 1), (-56, 2), (-56, 3)]


async def test_send_and_schedule_replies_and_schedules_both_messages(fake_context):
    from handlers import duel

    reply_markup = object()
    message = SimpleNamespace(
        message_id=70,
        reply_text=AsyncMock(return_value=SimpleNamespace(message_id=71)),
    )
    update = SimpleNamespace(
        message=message,
        effective_chat=SimpleNamespace(id=-57),
    )

    await duel.send_and_schedule(
        update,
        fake_context,
        "response text",
        reply_markup=reply_markup,
        parse_mode="MarkdownV2",
    )

    message.reply_text.assert_awaited_once_with(
        "response text",
        parse_mode="MarkdownV2",
        reply_markup=reply_markup,
    )
    assert fake_context.job_queue.calls == [
        (
            duel.delete_messages_job,
            duel.AUTO_DELETE_DELAY,
            {"data": {"chat_id": -57, "message_ids": [71, 70]}},
        )
    ]


async def test_send_and_schedule_falls_back_to_bot_send_message(fake_context):
    from handlers import duel

    reply_markup = object()
    message = SimpleNamespace(
        message_id=80,
        reply_text=AsyncMock(side_effect=RuntimeError("reply failed")),
    )
    update = SimpleNamespace(
        message=message,
        effective_chat=SimpleNamespace(id=-58),
    )

    await duel.send_and_schedule(
        update,
        fake_context,
        "fallback text",
        reply_markup=reply_markup,
        parse_mode="HTML",
    )

    fake_context.bot.send_message.assert_awaited_once_with(
        chat_id=-58,
        text="fallback text",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )
    assert fake_context.job_queue.calls == [
        (
            duel.delete_messages_job,
            duel.AUTO_DELETE_DELAY,
            {"data": {"chat_id": -58, "message_ids": [101, 80]}},
        )
    ]
