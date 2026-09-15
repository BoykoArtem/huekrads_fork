"""Hyperborean huy and Arthur event mechanics."""

import logging
import random
import sqlite3
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import format_user_title, get_all_chats, get_or_create_duel_user

HYPERBOREAN_HUY_CHANCE = 0.04
HYPERBOREAN_HUY_CHECK_MINUTES = 15
ACTIVE_HYPERBOREAN_EVENTS = {}
_HYPERBOREAN_DB_PATH = Path(__file__).resolve().parent.parent / "bot_database.db"

async def _spawn_hyperboreic_huy(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
):
    """
    С вероятностью HYPERBOREAN_HUY_CHANCE создаёт одно из двух событий:

    1. 🍆 Гиперборейский хуй
    2. ⚔️ Хуй Короля Артура

    Тип события выбирается случайно при каждом успешном появлении.
    """

    if chat_id in ACTIVE_HYPERBOREAN_EVENTS:
        return

    if random.random() >= HYPERBOREAN_HUY_CHANCE:
        return

    event_type = random.choice(
        [
            "hyperboreic",
            "arthur",
        ]
    )

    if event_type == "arthur":
        button_text = "⚔️ ХУЙ КОРОЛЯ АРТУРА"
        event_text = (
            "⚔️ <b>ОБНАРУЖЕН ХУЙ КОРОЛЯ АРТУРА</b>\n\n"
            "Кто осмелится вытащить его из камня?"
        )
    else:
        button_text = "🍆 ОБНАРУЖЕН ГИПЕРБОРЕЙСКИЙ ХУЙ"
        event_text = (
            "⚠️ <b>ОБНАРУЖЕН ГИПЕРБОРЕЙСКИЙ ХУЙ</b>\n\n"
            "Кто первый схватит — тому решать судьбу своего хуя."
        )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    button_text,
                    callback_data="hyperboreic_huy",
                )
            ]
        ]
    )

    try:
        message = await context.bot.send_message(
            chat_id=chat_id,
            text=event_text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception(
            "Не удалось создать событие %s в чате %s",
            event_type,
            chat_id,
        )
        return

    ACTIVE_HYPERBOREAN_EVENTS[chat_id] = {
        "message_id": message.message_id,
        "event_type": event_type,
    }


async def hyperboreic_huy_daily_job(
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    Независимый генератор события.

    Проверяется каждый чат, где бот уже зарегистрирован.
    На каждой проверке вероятность появления события = 4%.

    Если событие появилось, это случайно либо:
        - Гиперборейский хуй
        - Хуй Короля Артура
    """

    try:
        chats = get_all_chats()
    except Exception:
        logging.exception(
            "Не удалось получить список чатов для "
            "гиперборейского хуя"
        )
        return

    for chat_id in chats:
        try:
            await _spawn_hyperboreic_huy(
                context,
                chat_id,
            )
        except Exception:
            logging.exception(
                "Ошибка проверки гиперборейского хуя "
                "для чата %s",
                chat_id,
            )


def _claim_hyperboreic_huy(
    chat_id: int,
    tg_user,
):
    """
    Атомарно разрешает событие в БД.

    Возвращает:
        "restored" — у гнома не было хуя, он его вернул;
        "exploded" — хуй был, гном умер;
        "missing" — пользователя ещё нет в БД;
        "error" — ошибка БД.
    """

    user = get_or_create_duel_user(
        tg_user,
        chat_id,
    )

    user_id = int(user["user_id"])

    db_path = (
        _HYPERBOREAN_DB_PATH
    )

    try:
        with sqlite3.connect(
            str(db_path),
            timeout=10,
        ) as conn:
            cursor = conn.execute(
                """
                SELECT
                    dick_stolen_today,
                    points
                FROM duel_users
                WHERE chat_id = ?
                  AND user_id = ?
                """,
                (
                    chat_id,
                    user_id,
                ),
            )

            row = cursor.fetchone()

            if not row:
                return "missing"

            had_no_dick = bool(row[0])

            if had_no_dick:
                conn.execute(
                    """
                    UPDATE duel_users
                    SET dick_stolen_today = 0
                    WHERE chat_id = ?
                      AND user_id = ?
                    """,
                    (
                        chat_id,
                        user_id,
                    ),
                )
                return "restored"

            conn.execute(
                """
                UPDATE duel_users
                SET
                    points = 0,
                    dick_stolen_today = 1
                WHERE chat_id = ?
                  AND user_id = ?
                """,
                (
                    chat_id,
                    user_id,
                ),
            )
            return "exploded"

    except Exception:
        logging.exception(
            "Ошибка разрешения события гиперборейского хуя "
            "для user_id=%s chat_id=%s",
            user_id,
            chat_id,
        )
        return "error"


async def hyperboreic_huy_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not query or query.data != "hyperboreic_huy":
        return

    chat_id = update.effective_chat.id
    event = ACTIVE_HYPERBOREAN_EVENTS.get(chat_id)

    if not event:
        await query.answer(
            "Хуй уже унесли.",
            show_alert=True,
        )
        return

    # Сразу блокируем событие в памяти.
    # Только один игрок сможет его забрать.
    ACTIVE_HYPERBOREAN_EVENTS.pop(chat_id, None)

    event_type = event.get("event_type", "hyperboreic")

    result = _claim_hyperboreic_huy(
        chat_id,
        query.from_user,
    )

    if result == "error":
        ACTIVE_HYPERBOREAN_EVENTS[chat_id] = event

        await query.answer(
            "Хуй отказался определяться. Попробуй ещё раз.",
            show_alert=True,
        )
        return

    if result == "missing":
        await query.answer(
            "Гном ещё не зарегистрирован в этом чате.",
            show_alert=True,
        )
        return

    title = format_user_title(
        get_or_create_duel_user(
            query.from_user,
            chat_id,
        )
    )

    try:
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=event["message_id"],
            reply_markup=None,
        )
    except Exception:
        logging.exception(
            "Не удалось убрать кнопку события "
            "в чате %s",
            chat_id,
        )

    # ========================================================
    # ХУЙ БЫЛ УКРАДЕН — ИГРОК ПЫТАЕТСЯ ВЫТАЩИТЬ ЕГО
    # ========================================================

    if result == "restored":

        if event_type == "arthur":
            await query.answer(
                "НЕ СМОГ ВЫТАЩИТЬ ХУЙ КОРОЛЯ АРТУРА. НО ОН ВСЁ РАВНО ВЕРНУЛСЯ! 🍆",
                show_alert=True,
            )

            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"⚔️ <b>{title}</b> попытался вытащить "
                        f"<b>ХУЙ КОРОЛЯ АРТУРА</b>.\n\n"
                        "❌ Не смог вытащить хуй.\n\n"
                        "Но легендарный хуй каким-то образом "
                        "сам вернулся к своему владельцу.\n\n"
                        "🍆 <b>ХУЙ ВСЁ РАВНО ВОЗВРАЩЁН.</b>"
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                logging.exception(
                    "Не удалось отправить сообщение о возвращении "
                    "хуя Короля Артура в чате %s",
                    chat_id,
                )

            return

        await query.answer(
            "ХУЙ ВОЗВРАЩЁН! 🍆",
            show_alert=True,
        )

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🍆 <b>{title}</b> схватил гиперборейский хуй "
                    f"и вернул себе свой собственный."
                ),
                parse_mode="HTML",
            )
        except Exception:
            logging.exception(
                "Не удалось отправить сообщение о возвращении "
                "гиперборейского хуя в чате %s",
                chat_id,
            )

        return

    # ========================================================
    # У ИГРОКА УЖЕ ЕСТЬ ХУЙ — ХУЙ РАЗРЫВАЕТ ЕГО НА МОЛЕКУЛЫ
    # ========================================================

    if event_type == "arthur":
        await query.answer(
            "НЕ СМОГ ВЫТАЩИТЬ ХУЙ КОРОЛЯ АРТУРА. ТЕБЯ РАЗОРВАЛО НА ВЕЛИЧЕСТВЕННЫЕ ХУЙНЫЕ МОЛЕКУЛЫ.",
            show_alert=True,
        )

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⚔️ <b>{title}</b> попытался вытащить "
                    f"<b>ХУЙ КОРОЛЯ АРТУРА</b>.\n\n"
                    "❌ Не смог вытащить хуй.\n\n"
                    "💥 Но Хуй Короля Артура не потерпел "
                    "такого надругательства над своим величием.\n\n"
                    "Тело гнома разорвало на "
                    "<b>величественные хуйные молекулы</b>.\n\n"
                    "💀 Очки: <b>0 / 100</b>\n"
                    "🍆 Хуй: <b>УНИЧТОЖЕН</b>"
                ),
                parse_mode="HTML",
            )
        except Exception:
            logging.exception(
                "Не удалось отправить сообщение о взрыве "
                "от хуя Короля Артура в чате %s",
                chat_id,
            )

        return

    # ========================================================
    # ОБЫЧНЫЙ ГИПЕРБОРЕЙСКИЙ ХУЙ
    # ========================================================

    await query.answer(
        "ТЕБЯ РАЗОРВАЛО НА ХУЙНЫЕ МОЛЕКУЛЫ.",
        show_alert=True,
    )

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"💥 <b>{title}</b> попытался схватить "
                f"гиперборейский хуй.\n\n"
                "От передозировки хуев гнома разорвало "
                "на хуйные молекулы.\n\n"
                "💀 Очки: <b>0 / 100</b>\n"
                "🍆 Хуй: <b>потерян</b>"
            ),
            parse_mode="HTML",
        )
    except Exception:
        logging.exception(
            "Не удалось отправить сообщение о взрыве "
            "гнома в чате %s",
            chat_id,
        )
