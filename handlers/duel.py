import asyncio
import json
import logging
import random
import sqlite3
from datetime import datetime, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes
from config import (
    TOP_SORT_BY,
    ADMIN_IDS,
    WINNER_100_PTS_GIF,
    MAX_DAILY_POINTS,
    DUEL_TIMEZONE,
)
from database import (
    get_or_create_duel_user,
    get_duel_user_by_username,
    delete_duel_user_by_username,
    execute_duel_transaction,
    get_duel_top,
    format_user_title,
    get_dick_steal_chance,
    get_all_chats,
    reward_boss_victory,
    get_bosses_defeated,
    is_boss_enabled,
    set_boss_enabled,
)

AUTO_DELETE_DELAY = 60
MOVE_TIMEOUT = 10  # 10 секунд на ход

_DWARFS_FACTS_PATH = Path(__file__).resolve().parent.parent / "data" / "dwarfs_facts.json"
with open(_DWARFS_FACTS_PATH, encoding="utf-8") as _facts_file:
    DWARFS_FACTS = tuple(json.load(_facts_file)["facts"])


# ============================================================
# АКТИВНЫЕ ДУЭЛИ
# ============================================================

# Хранилище активных дуэлей в памяти:
# ACTIVE_DUELS[chat_id] = duel_state
#
# В одном чате одновременно может идти только одна дуэль.
ACTIVE_DUELS = {}

# ============================================================
# 🍆 ГИПЕРБОРЕЙСКИЙ ХУЙ
# ============================================================

HYPERBOREAN_HUY_CHANCE = 0.04

# Проверяем независимо от игровых событий раз в 15 минут.
# Это не дневной лимит: после полуночи вероятность не обнуляется.
HYPERBOREAN_HUY_CHECK_MINUTES = 15

# Одно активное событие на чат.
# Состояние живёт в памяти и не имеет ежедневного сброса.
ACTIVE_HYPERBOREAN_EVENTS = {}


# ============================================================
# 👹 АКТИВНЫЕ БИТВЫ С БОССАМИ
# ============================================================

# В одном чате одновременно может идти только одна битва с боссом.
#
# ACTIVE_BOSS_BATTLES[chat_id] = {
#     "boss": {...},
#     "participants": {
#         user_id: {
#             "tg_user": ...,
#             "data": {...},
#             "attack": None,
#             "block": None,
#             "alive": True,
#         }
#     },
#     "hits": 0,
#     "round": 0,
#     "phase": "join" / "battle",
#     "message_id": None,
#     "task": None,
#     "lock": asyncio.Lock(),
# }
ACTIVE_BOSS_BATTLES = {}

BOSS_JOIN_TIMEOUT = 60
BOSS_MOVE_TIMEOUT = 10
BOSS_REQUIRED_HITS = 5


BOSSES = [
    {
        "name": "Глубокорылый Барон",
        "emoji": "👹",
        "description": (
            "Древний владыка шахт. У него три подбородка, "
            "семь ножей и абсолютно нулевая терпимость к гномам."
        ),
    },
    {
        "name": "Хуекрушитель Мордогрыз",
        "emoji": "💀",
        "description": (
            "Монстр настолько злой, что однажды укусил собственную "
            "бороду и победил."
        ),
    },
    {
        "name": "Князь Подземного Пиздеца",
        "emoji": "👑",
        "description": (
            "Повелитель нижних штолен. Его корона сделана из "
            "сломанных гномьих ножей."
        ),
    },
    {
        "name": "Великий Ножебород",
        "emoji": "🧔",
        "description": (
            "Его борода настолько острая, что ею можно нарезать "
            "колбасу и участников."
        ),
    },
    {
        "name": "Пожиратель Хуев",
        "emoji": "🦷",
        "description": (
            "Никто не знает, сколько хуев он уже съел. "
            "Сам он тоже не знает. Он просто продолжает."
        ),
    },
]


# ============================================================
# СЛОВАРИ ДЛЯ КНОПОК И ТЕКСТА
# ============================================================

TARGET_NAMES = {
    "head": "Голова 🧠",
    "body": "Торс 🛡️",
    "dick": "Хуй 🍆",
}


ATTACK_PHRASES = [
    "замахивается засапожным свинорезом",
    "делает резкий подрез тяжелым поджильным ножом",
    "целится заточенным шахтерским скальпелем",
    "выполняет молниеносный выпад кованым джамбием",
    "пытается нанести коварный тычок под ребро",
    "выполняет убойный подрез кузнечным лезвием",
    "крутит подлый финт короткой гномьей заточкой",
]


HIT_PHRASES = [
    "с хрустом вонзает гномью сталь прямо в цель!",
    "пробивает промасленную жилетку и наносит сокрушительный порез!",
    "находит незащищенную складку и чисто пробивает оборону!",
    "сбивает соперника с ног коротким боковым подрезом!",
    "завершает пивную потасовку точнейшим тычком!",
]


BLOCK_PHRASES = [
    "успевает подставить тяжелый обух и сбивает траекторию!",
    "слышит звон стали — встречает клинок массивным набалдашником ножа!",
    "принимает удар на толстый кожаный наруч и хохочет!",
    "предугадывает подлость и блокирует выпад широким лезвием!",
    "перехватывает запястье сухой мозолистой рукой!",
]


MISS_PHRASES = [
    "поскальзывается на пролитом эле и режет воздух!",
    "теряет равновесие и чиркает ножом по мифриловой жиле!",
    "промахивается в миллиметре от цели и режет собственное голенище!",
    "зацепляется сапогом за пень и шлепается брюхом в грязь!",
    "выпускает нож из засаленных от рульки ладоней!",
]


SUICIDE_PHRASES = [
    "пытается сделать эльфийский финт, но вонзает свинорез себе в колено!",
    "спотыкается о собственную бороду и натыкается на свое же лезвие!",
    "решает подбросить нож для понтов, но ловит его печенью!",
    "выполняет опасный кувырок и случайно подрезает сам себе жилы!",
    "переусердствовал с замахом и вырубает себя тяжелой рукоятью!",
]


def _plural_rounds(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "раунд"
    if 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
        return "раунда"
    return "раундов"


def get_round_flavor_text(rounds_count: int) -> str:
    if rounds_count <= 1:
        phrases = [
            "⚡ <b>Срезал в касание!</b> Противник даже не успел понять, что произошло.",
            "🚀 <b>Ваншот!</b> Одно мгновение — и дуэль окончена.",
            "🎯 <b>Быстрый чек!</b> Вышел, зарезал, ушел.",
            "🐟 <b>Тюленьим жиром по лбу!</b> Противник упал, потому что был намазан, а не потому что больно.",
            "🎺 <b>Трубач играл!</b> Играл так громко, что у врага лопнули барабанные перепонки — и душа заодно.",
            "🍑 <b>Удар жопой!</b> Гном развернулся, подпрыгнул и приземлился задом на голову противника. Тот сдох от унижения.",
            "🌀 <b>Смерч из бороды!</b> Завертелся, как вентилятор — врага разорвало в клочья статическим электричеством.",
            "🧦 <b>Вонючим носком в лицо!</b> Удар был не смертелен, но запах убил мгновенно. Противник задохнулся от отвращения.",
            "🦆 <b>Утка-крякалка!</b> Гном достал резиновую утку, крякнул — врага парализовало. Добил уткой же.",
            "🪑 <b>Табуреткой по короне!</b> Откуда табуретка? Никто не знает. Но череп треснул.",
            "🎣 <b>На крючок!</b> Поймал врага за бороду, дернул — и тот улетел в стратосферу. Счастливого пути!",
            "🧠 <b>Вынул мозги через ухо!</b> Как ушную серу, только краснее и с криками.",
            "🥚 <b>Яйцом по голове!</b> Обычным куриным. Врага стошнило, он упал и захлебнулся желтком. Позорная смерть.",
        ]
    elif rounds_count <= 4:
        phrases = [
            "⚔️ <b>Быстрая рубка!</b> Гномы едва успели запыхаться.",
            "🔥 <b>Короткий, но яркий бой!</b> Искры летели во все стороны.",
            "🍺 <b>Даже пиво не остыло!</b> Скоротечная схватка.",
            "🦷 <b>Зубная фея пришла!</b> Выбил все зубы и положил под подушку. Подушки не было, так что положил в карман врагу. Тот упал от недоумения.",
            "🧹 <b>Помелом по спине!</b> Кто принес метлу? Гном-дворник. Просто проходил мимо.",
            "🍌 <b>Поскользнулся на шкурке!</b> Противник упал, насадился на собственный топор и сдох. Ирония? Нет, просто банан.",
            "🔔 <b>Колокольчик!</b> Позвенел, враг застыл как вкопанный. Гном аккуратно снял с него шкуру и сделал коврик.",
            "🦞 <b>Крабовая атака!</b> Гном достал живого краба и щипнул врага за яйца. Тот закричал на полтона выше.",
            "🪣 <b>Ведро на голову!</b> Противник ослеп, споткнулся о собственные ноги и сломал шею. Ведро — MVP.",
            "🧀 <b>Сыр в лицо!</b> Липкий, вонючий, с плесенью. Враг подавился от отвращения и захлебнулся слюной.",
            "🦅 <b>Орел-мутант!</b> Гном свистнул, сверху упал орел, клюнул врага в глаз и улетел. Бой закончен.",
            "🪤 <b>Мышеловка!</b> Поставил на пути врага. Тот наступил, оторвало ногу. Гном собрал ногу и ушел.",
            "🎈 <b>Воздушный шарик!</b> Лопнул над ухом врага. Тот подпрыгнул, ударился головой о люстру и умер. А люстра была, блять.",
        ]
    elif rounds_count <= 8:
        phrases = [
            "🛡️ <b>Плотное рубилово!</b> Достойный поединок двух мастеров.",
            "💥 <b>Затяжная дуэль!</b> Борода против бороды, топор против топора.",
            "🩸 <b>Потная заруба!</b> Оба гнома оставили немало сил на арене.",
            "🧸 <b>Плюшевым мишкой по спине!</b> Враг упал не от боли, а от шока — плюшевый мишка, серьезно?",
            "🪥 <b>Зубной щеткой!</b> Чистил зубы, споткнулся, ткнул врага щеткой в горло. Тот задохнулся от мятной свежести.",
            "🧻 <b>Рулон туалетной бумаги!</b> Размотал, обмотал врага, тот упал как мумия. Гном вытолкал его со сцены ногой.",
            "🥕 <b>Морковкой в глаз!</b> Обычной морковкой. Враг моргнул — и ослеп. Морковь сломалась. Все в шоке.",
            "🎻 <b>Скрипка!</b> Заиграл так фальшиво, что у врага лопнули уши, пошла кровь, и он скончался от мучительной боли в душе.",
            "🪚 <b>Пила, но пилит не кость, а воздух.</b> Противник просто упал от усталости, пока гном пилил рядом. Техническая победа.",
            "🐸 <b>Жаба!</b> Гном засунул жабу в рот врагу. Тот задохнулся, потому что жаба была жирная.",
            "🎣 <b>Удочка!</b> Поймал врага за бороду и начал подтягивать к себе. Враг сопротивлялся, споткнулся и сломал позвоночник.",
            "🧊 <b>Кубик льда!</b> Засунул за шиворот врагу. Тот подпрыгнул, ударился головой о свой же топор и умер. Холод убил.",
            "📌 <b>Кнопка!</b> Уколол в пятку. Враг упал, как тронутый. Ахиллес? Нет, просто канцелярская кнопка.",
        ]
    else:
        phrases = [
            "👵 <b>Дедовская осада!</b> Бой длился так долго, что у участников выросли новые бороды.",
            "🐌 <b>Эпическая тягомотина!</b> Зрители успели уснуть и проснуться.",
            "🪨 <b>Встретились два камня!</b> Это была дуэль на измор.",
            "🌌 <b>Черная дыра!</b> Гном открыл рот, засосал туда половину арены, включая врага. Потом закрыл и рыгнул.",
            "⏳ <b>Машина времени!</b> Гном перенесся в прошлое и убил врага в детстве. На арене остался пыльный след и парадокс.",
            "🤖 <b>Робот-гном!</b> Нажал кнопку на груди, из глаз вылетели лазеры, испепелили врага. Но гном сел на батарейках.",
            "🍕 <b>Пицца!</b> Кинул горячей пиццей в лицо. Враг обварился и умер от ожогов. А пицца была вкусная.",
            "🎮 <b>Контроллер!</b> Гном нажал 'Alt+F4', и враг просто исчез. Реальность вылетела.",
            "🧙 <b>Магия, но не магия!</b> Гном просто сказал: 'Ты уже умер'. Враг спорил три часа, но потом все-таки сдох от спора.",
            "🦄 <b>Единорог!</b> Прискакал, ткнул врага рогом в пупок и ускакал. Враг истек радужной кровью.",
            "🪐 <b>Сатурн!</b> Гном достал кольцо Сатурна, намотал на шею врагу и затянул. Тот задохнулся в космическом пространстве. На арене.",
            "📦 <b>Ящик с надписью 'Сюрприз'!</b> Внутри был второй ящик. Внутри второго — третий. Враг открывал три часа, устал и умер сам.",
            "🧩 <b>Пазл!</b> Гном разобрал врага на части, как конструктор, а потом собрал заново, но неправильно. Враг ходил задом наперед, споткнулся и сломался окончательно.",
        ]
    return random.choice(phrases)


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

async def delete_messages_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data.get("chat_id")
    message_ids = job_data.get("message_ids", [])

    for msg_id in message_ids:
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=msg_id,
            )
        except Exception:
            pass


def schedule_auto_delete(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_ids: list[int],
):
    if context.job_queue:
        context.job_queue.run_once(
            delete_messages_job,
            when=AUTO_DELETE_DELAY,
            data={
                "chat_id": chat_id,
                "message_ids": message_ids,
            },
        )


def _extract_username(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> str | None:

    if context.args:
        return context.args[0].strip().lstrip("@")

    if update.message and update.message.text:
        parts = update.message.text.split()

        if len(parts) > 1:
            return parts[1].strip().lstrip("@")

    return None


async def send_and_schedule(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: InlineKeyboardMarkup = None,
    parse_mode: str = "HTML",
):
    chat_id = update.effective_chat.id

    msg_id_to_delete = (
        update.message.message_id
        if update.message
        else None
    )

    try:
        if update.message:
            bot_msg = await update.message.reply_text(
                text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
        else:
            bot_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )

    except Exception:
        bot_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )

    to_delete = [bot_msg.message_id]

    if msg_id_to_delete:
        to_delete.append(msg_id_to_delete)

    schedule_auto_delete(
        context,
        chat_id=chat_id,
        message_ids=to_delete,
    )


# ============================================================
# КЛАВИАТУРЫ
# ============================================================

def _get_strike_keyboard(turn_id: int) -> InlineKeyboardMarkup:
    """
    Кнопки атаки привязаны к конкретному turn_id.

    Благодаря этому старая клавиатура от предыдущего хода
    не сможет выполнить действие в новом ходе.
    """

    buttons = [
        [
            InlineKeyboardButton(
                "🎯 Голова",
                callback_data=f"duel_strike_head_{turn_id}",
            ),
            InlineKeyboardButton(
                "🛡️ Торс",
                callback_data=f"duel_strike_body_{turn_id}",
            ),
            InlineKeyboardButton(
                "🍆 Хуй",
                callback_data=f"duel_strike_dick_{turn_id}",
            ),
        ]
    ]

    return InlineKeyboardMarkup(buttons)


def _get_block_keyboard(turn_id: int) -> InlineKeyboardMarkup:
    """
    Кнопки защиты привязаны к конкретному turn_id.
    """

    buttons = [
        [
            InlineKeyboardButton(
                "🛡️ Голова",
                callback_data=f"duel_block_head_{turn_id}",
            ),
            InlineKeyboardButton(
                "🛡️ Торс",
                callback_data=f"duel_block_body_{turn_id}",
            ),
            InlineKeyboardButton(
                "🛡️ Хуй",
                callback_data=f"duel_block_dick_{turn_id}",
            ),
        ]
    ]

    return InlineKeyboardMarkup(buttons)


# ============================================================
# НАЧАЛО ИНТЕРАКТИВНОГО БОЯ
# ============================================================

async def _start_interactive_fight(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    attacker_tg,
    defender_tg,
    attacker_data: dict,
    defender_data: dict,
    original_msg_id: int = None,
):

    duel_state = {
        "attacker_tg": attacker_tg,
        "defender_tg": defender_tg,

        "attacker_data": attacker_data,
        "defender_data": defender_data,

        # Текущая фаза:
        # attack = атакующий выбирает атаку
        # block = защищающийся выбирает блок
        "phase": "attack",

        "attack_zone": None,

        "round": 1,

        # Уникальный номер текущего хода.
        # Меняется при каждом переходе к следующему ходу.
        "turn_id": 1,

        "message_id": None,

        "turn_task": None,

        # Защита от двух одновременных callback.
        "lock": asyncio.Lock(),

        "original_msg_id": original_msg_id,
    }

    ACTIVE_DUELS[chat_id] = duel_state

    att_title = format_user_title(attacker_data)
    def_title = format_user_title(defender_data)

    text = (
        f"🗡️ <b>Гномья дуэль начинается!</b>\n\n"
        f"⚔️ Атакует: <b>{att_title}</b>\n"
        f"🛡️ Защищается: <b>{def_title}</b>\n\n"
        f"⏳ У <b>{att_title}</b> есть {MOVE_TIMEOUT} секунд, "
        f"чтобы выбрать точку удара:"
    )

    bot_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=_get_strike_keyboard(
            duel_state["turn_id"]
        ),
    )

    duel_state["message_id"] = bot_msg.message_id

    task = asyncio.create_task(
        _auto_move_timer(
            context,
            chat_id,
            duel_state["round"],
            phase="attack",
            turn_id=duel_state["turn_id"],
        )
    )

    duel_state["turn_task"] = task


# ============================================================
# АВТОМАТИЧЕСКИЙ ХОД ПО ТАЙМАУТУ
# ============================================================

async def _auto_move_timer(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    round_num: int,
    phase: str,
    turn_id: int,
):

    await asyncio.sleep(MOVE_TIMEOUT)

    duel = ACTIVE_DUELS.get(chat_id)

    if not duel:
        return

    async with duel["lock"]:

        # Проверяем абсолютно все параметры текущего хода.
        #
        # Это важно: старый таймер не должен вмешаться
        # в новый раунд или новый ход.
        if (
            duel.get("round") != round_num
            or duel.get("phase") != phase
            or duel.get("turn_id") != turn_id
        ):
            return

        random_choice = random.choice(
            ["head", "body", "dick"]
        )

        if phase == "attack":

            att_title = format_user_title(
                duel["attacker_data"]
            )

            try:
                timeout_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"⏰ <b>{att_title}</b> зазевался! "
                        f"Гномий синедрион делает случайный "
                        f"выбор атаки..."
                    ),
                    parse_mode="HTML",
                )
                schedule_auto_delete(
                    context,
                    chat_id,
                    [timeout_msg.message_id],
                )
            except Exception:
                pass

            await _process_attack_choice(
                context,
                chat_id,
                random_choice,
            )

        elif phase == "block":

            def_title = format_user_title(
                duel["defender_data"]
            )

            try:
                timeout_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"⏰ <b>{def_title}</b> зазевался! "
                        f"Гномий синедрион делает случайный "
                        f"выбор блока..."
                    ),
                    parse_mode="HTML",
                )
                schedule_auto_delete(
                    context,
                    chat_id,
                    [timeout_msg.message_id],
                )
            except Exception:
                pass

            await _process_block_choice(
                context,
                chat_id,
                random_choice,
            )


# ============================================================
# CALLBACK-КНОПКИ АТАКИ / ЗАЩИТЫ
# ============================================================

async def duel_strike_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not query or not query.data:
        return

    chat_id = update.effective_chat.id
    duel = ACTIVE_DUELS.get(chat_id)

    if not duel:
        await query.answer(
            "Дуэль не найдена или уже завершена.",
            show_alert=True,
        )
        return

    # ВАЖНО:
    # Все проверки и изменение состояния находятся
    # внутри одного lock.
    #
    # Если пользователь очень быстро нажмет две кнопки,
    # второй callback дождется первого и увидит уже
    # измененную фазу.
    async with duel["lock"]:

        callback_data = query.data
        user_id = query.from_user.id

        # ====================================================
        # АТАКА
        # ====================================================

        if callback_data.startswith("duel_strike_"):

            # Сейчас не фаза атаки.
            if duel["phase"] != "attack":
                await query.answer(
                    "Сейчас не ваш ход. Ждите защиты соперника.",
                    show_alert=True,
                )
                return

            # Только атакующий может выбирать атаку.
            if user_id != duel["attacker_tg"].id:
                await query.answer(
                    "Сейчас не ваш ход для атаки!",
                    show_alert=True,
                )
                return

            # Ожидаем:
            # duel_strike_head_1
            # duel_strike_body_1
            # duel_strike_dick_1

            parts = callback_data.split("_")

            if len(parts) != 4:
                await query.answer(
                    "Эта кнопка устарела.",
                    show_alert=True,
                )
                return

            strike_zone = parts[2]

            try:
                button_turn_id = int(parts[3])
            except ValueError:
                await query.answer(
                    "Эта кнопка устарела.",
                    show_alert=True,
                )
                return

            # Кнопка должна принадлежать именно текущему ходу.
            if button_turn_id != duel["turn_id"]:
                await query.answer(
                    "Этот ход уже закончился.",
                    show_alert=True,
                )
                return

            if strike_zone not in TARGET_NAMES:
                await query.answer(
                    "Неизвестная зона атаки.",
                    show_alert=True,
                )
                return

            # Все проверки прошли.
            # Теперь отменяем таймер.
            if (
                duel.get("turn_task")
                and not duel["turn_task"].done()
            ):
                duel["turn_task"].cancel()

            await query.answer()

            await _process_attack_choice(
                context,
                chat_id,
                strike_zone,
            )

            return

        # ====================================================
        # ЗАЩИТА
        # ====================================================

        if callback_data.startswith("duel_block_"):

            # Сейчас не фаза защиты.
            if duel["phase"] != "block":
                await query.answer(
                    "Сейчас не ваш ход. Ждите атаки соперника.",
                    show_alert=True,
                )
                return

            # Только защищающийся может выбирать защиту.
            if user_id != duel["defender_tg"].id:
                await query.answer(
                    "Сейчас не ваш ход для защиты!",
                    show_alert=True,
                )
                return

            # Ожидаем:
            # duel_block_head_2
            # duel_block_body_2
            # duel_block_dick_2

            parts = callback_data.split("_")

            if len(parts) != 4:
                await query.answer(
                    "Эта кнопка устарела.",
                    show_alert=True,
                )
                return

            block_zone = parts[2]

            try:
                button_turn_id = int(parts[3])
            except ValueError:
                await query.answer(
                    "Эта кнопка устарела.",
                    show_alert=True,
                )
                return

            # Кнопка должна принадлежать текущему ходу.
            if button_turn_id != duel["turn_id"]:
                await query.answer(
                    "Этот ход уже закончился.",
                    show_alert=True,
                )
                return

            if block_zone not in TARGET_NAMES:
                await query.answer(
                    "Неизвестная зона защиты.",
                    show_alert=True,
                )
                return

            if (
                duel.get("turn_task")
                and not duel["turn_task"].done()
            ):
                duel["turn_task"].cancel()

            await query.answer()

            await _process_block_choice(
                context,
                chat_id,
                block_zone,
            )

            return


# Алиас для совместимости с bot.py
duel_action_callback = duel_strike_callback


# ============================================================
# ОБРАБОТКА АТАКИ
# ============================================================

async def _process_attack_choice(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    strike_zone: str,
):

    duel = ACTIVE_DUELS.get(chat_id)

    if not duel:
        return

    duel["attack_zone"] = strike_zone

    # Теперь ход принадлежит защищающемуся.
    duel["phase"] = "block"

    # Новый turn_id = новая клавиатура.
    duel["turn_id"] += 1

    att_title = format_user_title(
        duel["attacker_data"]
    )

    def_title = format_user_title(
        duel["defender_data"]
    )

    text = (
        f"🗡️ <b>Гномья дуэль! Раунд {duel['round']}</b>\n\n"
        f"⚔️ <b>{att_title}</b> наносит замах!\n"
        f"🛡️ <b>{def_title}</b>, выберите зону защиты!\n\n"
        f"⏳ У <b>{def_title}</b> есть {MOVE_TIMEOUT} секунд "
        f"на выбор блока:"
    )

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=duel["message_id"],
            text=text,
            parse_mode="HTML",
            reply_markup=_get_block_keyboard(
                duel["turn_id"]
            ),
        )

    except Exception:

        bot_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=_get_block_keyboard(
                duel["turn_id"]
            ),
        )

        duel["message_id"] = bot_msg.message_id

    task = asyncio.create_task(
        _auto_move_timer(
            context,
            chat_id,
            duel["round"],
            phase="block",
            turn_id=duel["turn_id"],
        )
    )

    duel["turn_task"] = task


# ============================================================
# ОБРАБОТКА ЗАЩИТЫ
# ============================================================

async def _process_block_choice(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    block_zone: str,
):

    duel = ACTIVE_DUELS.get(chat_id)

    if not duel:
        return

    strike_zone = duel["attack_zone"]

    attacker_data = duel["attacker_data"]
    defender_data = duel["defender_data"]

    att_title = format_user_title(attacker_data)
    def_title = format_user_title(defender_data)

    # ========================================================
    # 1. Шанс 1% — самоубийство атаковавшего
    # ========================================================

    if random.random() < 0.01:

        suicide_phrase = random.choice(
            SUICIDE_PHRASES
        )

        res_text = (
            f"💥 <b>НЕВЕРОЯТНЫЙ ИСХОД!</b>\n\n"
            f"<b>{att_title}</b> {suicide_phrase}\n\n"
            f"🏆 Победитель по глупости соперника: "
            f"<b>{def_title}</b>!"
        )

        await _finish_duel(
            context,
            chat_id,
            winner=defender_data,
            loser=attacker_data,
            custom_text=res_text,
            strike_zone=strike_zone,
            block_zone=block_zone,
        )

        return

    # ========================================================
    # 2. Шанс 5% — промах
    # ========================================================

    if random.random() < 0.05:

        miss_phrase = random.choice(
            MISS_PHRASES
        )

        att_action = random.choice(
            ATTACK_PHRASES
        )

        # Смена ролей.
        duel["attacker_tg"], duel["defender_tg"] = (
            duel["defender_tg"],
            duel["attacker_tg"],
        )

        duel["attacker_data"], duel["defender_data"] = (
            duel["defender_data"],
            duel["attacker_data"],
        )

        duel["phase"] = "attack"
        duel["attack_zone"] = None
        duel["round"] += 1

        # Новый ход = новая кнопка.
        duel["turn_id"] += 1

        new_att_title = format_user_title(
            duel["attacker_data"]
        )

        new_def_title = format_user_title(
            duel["defender_data"]
        )

        text = (
            f"💨 <b>ПРОМАХ!</b>\n"
            f"<b>{att_title}</b> {att_action} "
            f"в зону ({TARGET_NAMES[strike_zone]}), "
            f"но {miss_phrase}\n\n"
            f"🔄 <b>Смена ролей!</b>\n"
            f"⚔️ Атакует: <b>{new_att_title}</b>\n"
            f"🛡️ Защищается: <b>{new_def_title}</b>\n\n"
            f"⏳ У <b>{new_att_title}</b> есть "
            f"{MOVE_TIMEOUT} секунд на удар:"
        )

        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=duel["message_id"],
                text=text,
                parse_mode="HTML",
                reply_markup=_get_strike_keyboard(
                    duel["turn_id"]
                ),
            )

        except Exception:

            bot_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=_get_strike_keyboard(
                    duel["turn_id"]
                ),
            )

            duel["message_id"] = bot_msg.message_id

        task = asyncio.create_task(
            _auto_move_timer(
                context,
                chat_id,
                duel["round"],
                phase="attack",
                turn_id=duel["turn_id"],
            )
        )

        duel["turn_task"] = task

        return

    # ========================================================
    # 3. Сравнение УДАРА и БЛОКА
    # ========================================================

    if strike_zone == block_zone:

        block_phrase = random.choice(
            BLOCK_PHRASES
        )

        att_action = random.choice(
            ATTACK_PHRASES
        )

        # Смена ролей.
        duel["attacker_tg"], duel["defender_tg"] = (
            duel["defender_tg"],
            duel["attacker_tg"],
        )

        duel["attacker_data"], duel["defender_data"] = (
            duel["defender_data"],
            duel["attacker_data"],
        )

        duel["phase"] = "attack"
        duel["attack_zone"] = None
        duel["round"] += 1

        # Новый ход = новая кнопка.
        duel["turn_id"] += 1

        new_att_title = format_user_title(
            duel["attacker_data"]
        )

        new_def_title = format_user_title(
            duel["defender_data"]
        )

        text = (
            f"🛡️ <b>БЛОК СРАБОТАЛ!</b>\n"
            f"<b>{att_title}</b> {att_action} "
            f"в зону ({TARGET_NAMES[strike_zone]}), "
            f"но <b>{def_title}</b> {block_phrase}\n\n"
            f"🔄 <b>Инициатива переходит!</b>\n"
            f"⚔️ Атакует: <b>{new_att_title}</b>\n"
            f"🛡️ Защищается: <b>{new_def_title}</b>\n\n"
            f"⏳ У <b>{new_att_title}</b> есть "
            f"{MOVE_TIMEOUT} секунд на удар:"
        )

        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=duel["message_id"],
                text=text,
                parse_mode="HTML",
                reply_markup=_get_strike_keyboard(
                    duel["turn_id"]
                ),
            )

        except Exception:

            bot_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=_get_strike_keyboard(
                    duel["turn_id"]
                ),
            )

            duel["message_id"] = bot_msg.message_id

        task = asyncio.create_task(
            _auto_move_timer(
                context,
                chat_id,
                duel["round"],
                phase="attack",
                turn_id=duel["turn_id"],
            )
        )

        duel["turn_task"] = task

    # ========================================================
    # 4. Точный удар
    # ========================================================

    else:

        hit_phrase = random.choice(
            HIT_PHRASES
        )

        att_action = random.choice(
            ATTACK_PHRASES
        )

        res_text = (
            f"💥 <b>ТОЧНЫЙ УДАР!</b>\n"
            f"<b>{att_title}</b> {att_action} "
            f"в зону ({TARGET_NAMES[strike_zone]}), "
            f"а <b>{def_title}</b> блокировал "
            f"({TARGET_NAMES[block_zone]}).\n"
            f"<b>{att_title}</b> {hit_phrase}\n"
        )

        await _finish_duel(
            context,
            chat_id,
            winner=attacker_data,
            loser=defender_data,
            custom_text=res_text,
            strike_zone=strike_zone,
            block_zone=block_zone,
        )


# ============================================================
# ЗАВЕРШЕНИЕ ДУЭЛИ
# ============================================================

async def _spawn_hyperboreic_huy(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
):
    """
    С вероятностью 4% создаёт событие «ОБНАРУЖЕН ГИПЕРБОРЕЙСКИЙ ХУЙ».

    Функция вызывается отдельным периодическим заданием JobQueue,
    независимо от дуэлей, боссов и любых других игровых событий.

    Шанс не является дневным счётчиком и не сбрасывается раз в сутки.
    Само событие существует до первого успешного нажатия.
    """
    if chat_id in ACTIVE_HYPERBOREAN_EVENTS:
        return

    if random.random() >= HYPERBOREAN_HUY_CHANCE:
        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🍆 ОБНАРУЖЕН ГИПЕРБОРЕЙСКИЙ ХУЙ",
                    callback_data="hyperboreic_huy",
                )
            ]
        ]
    )

    try:
        message = await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ <b>ОБНАРУЖЕН ГИПЕРБОРЕЙСКИЙ ХУЙ</b>\n\n"
                "Кто первый схватит — тому решать судьбу своего хуя."
            ),
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception(
            "Не удалось создать событие гиперборейского хуя "
            "в чате %s",
            chat_id,
        )
        return

    ACTIVE_HYPERBOREAN_EVENTS[chat_id] = {
        "message_id": message.message_id,
    }


async def hyperboreic_huy_daily_job(
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    Независимый генератор события.

    Проверяется каждый чат, где бот уже зарегистрирован.
    На каждой проверке вероятность появления события = 4%.
    Никаких ежедневных сбросов нет.
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
        Path(__file__).resolve().parent.parent / "bot_database.db"
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
            "Гиперборейский хуй уже унесли.",
            show_alert=True,
        )
        return

    # Сразу блокируем событие в памяти.
    # Это гарантирует, что победитель будет только один.
    ACTIVE_HYPERBOREAN_EVENTS.pop(chat_id, None)

    result = _claim_hyperboreic_huy(
        chat_id,
        query.from_user,
    )

    if result == "error":
        # Возвращаем событие, если БД временно недоступна.
        ACTIVE_HYPERBOREAN_EVENTS[chat_id] = event

        await query.answer(
            "Гиперборейский хуй отказался определяться. Попробуй ещё раз.",
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
            "Не удалось убрать кнопку гиперборейского хуя "
            "в чате %s",
            chat_id,
        )

    if result == "restored":
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


async def _finish_duel(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    winner: dict,
    loser: dict,
    custom_text: str,
    strike_zone: str = None,
    block_zone: str = None,
):

    duel = ACTIVE_DUELS.pop(chat_id, None)
    rounds_count = duel.get("round", 1) if duel else 1

    # Шанс кражи не зависит от раундов: база +1% за каждую победу
    # проигравшего за сегодня (накапливается, когда он побеждал).
    steal_chance = get_dick_steal_chance(loser.get("daily_wins", 0))
    is_dick_stolen = random.random() < steal_chance

    try:

        w_after, l_after = execute_duel_transaction(
            chat_id=chat_id,
            winner_user=winner,
            loser_user=loser,
            is_dick_stolen=is_dick_stolen,
        )

    except Exception:

        bot_msg = await context.bot.send_message(
            chat_id,
            "⚠️ Ошибка проведения дуэли. Попробуйте снова.",
        )

        schedule_auto_delete(
            context,
            chat_id,
            [bot_msg.message_id],
        )

        return

    win_title = format_user_title(winner)
    lose_title = format_user_title(loser)

    res_msg = (
        f"{custom_text}\n"
        f"🗡️ <b>Результаты дуэли:</b>\n\n"
        f"Победитель: <b>{win_title}</b>\n"
        f"Проигравший: <b>{lose_title}</b>\n\n"
        f"<b>{win_title}</b>: +10 очков "
        f"({w_after}/100)\n"
        f"<b>{lose_title}</b>: -5 очков "
        f"({l_after}/100)\n"
    )

    stats_text = (
        f"\n📊 Длительность: <b>{rounds_count}</b> "
        f"{_plural_rounds(rounds_count)}\n"
        f"{get_round_flavor_text(rounds_count)}\n"
    )

    if is_dick_stolen:

        fact = random.choice(
            DWARFS_FACTS
        )

        res_msg += (
            f"\n💀 <b>И ВДОБАВОК У НЕГО УКРАЛИ ХУЙ.</b>\n\n"
            f"Сегодня {lose_title} больше не может драться.\n"
            f"{stats_text}\n"
            f"📖 <i>{fact}</i>"
        )
    else:
        res_msg += stats_text

    if duel and duel.get("message_id"):

        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=duel["message_id"],
            )
        except Exception:
            pass

    bot_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=res_msg,
        parse_mode="HTML",
    )

    to_delete = []

    if not is_dick_stolen:
        to_delete.append(
            bot_msg.message_id
        )

    if duel and duel.get("original_msg_id"):
        to_delete.append(
            duel["original_msg_id"]
        )

    if to_delete:
        schedule_auto_delete(
            context,
            chat_id,
            to_delete,
        )

    reached_max = (
        winner["points"] < MAX_DAILY_POINTS
        and w_after >= MAX_DAILY_POINTS
    )

    if reached_max and WINNER_100_PTS_GIF:

        try:
            await context.bot.send_animation(
                chat_id=chat_id,
                animation=WINNER_100_PTS_GIF,
                caption=(
                    f"🏆 <b>{win_title}</b> набрал "
                    f"{MAX_DAILY_POINTS} очков!"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass


# ============================================================
# ПОИСК И НАЧАЛО ДУЭЛИ
# ============================================================

async def _process_duel_fight(
    context: ContextTypes.DEFAULT_TYPE,
    initiator_tg,
    target_username: str,
    chat_id: int,
    original_msg_id: int = None,
):

    if chat_id in ACTIVE_DUELS:

        bot_msg = await context.bot.send_message(
            chat_id,
            "⚔️ В этом чате уже идет дуэль! "
            "Дождитесь ее окончания.",
        )

        schedule_auto_delete(
            context,
            chat_id,
            [bot_msg.message_id],
        )

        return

    if (
        initiator_tg.username
        and initiator_tg.username.lower()
        == target_username.lower()
    ):

        bot_msg = await context.bot.send_message(
            chat_id,
            "⚔️ Нельзя вызвать на дуэль самого себя!",
        )

        schedule_auto_delete(
            context,
            chat_id,
            [bot_msg.message_id],
        )

        return

    initiator = get_or_create_duel_user(
        initiator_tg,
        chat_id,
    )

    init_title = format_user_title(
        initiator
    )

    if initiator["dick_stolen_today"]:

        bot_msg = await context.bot.send_message(
            chat_id,
            (
                f"💀 <b>{init_title}</b> сегодня уже "
                f"без хуя. До завтра драться нельзя."
            ),
            parse_mode="HTML",
        )

        schedule_auto_delete(
            context,
            chat_id,
            [bot_msg.message_id],
        )

        return

    if initiator["points"] <= 0:

        bot_msg = await context.bot.send_message(
            chat_id,
            "⚔️ У вас 0 очков. "
            "Вы больше не можете драться сегодня.",
        )

        schedule_auto_delete(
            context,
            chat_id,
            [bot_msg.message_id],
        )

        return

    opponent = get_duel_user_by_username(
        target_username,
        chat_id,
    )

    if not opponent:

        bot_msg = await context.bot.send_message(
            chat_id,
            (
                f"❌ Пользователь <b>{target_username}</b> "
                f"не найден в базе этого чата."
            ),
            parse_mode="HTML",
        )

        schedule_auto_delete(
            context,
            chat_id,
            [bot_msg.message_id],
        )

        return

    if opponent["user_id"] == initiator["user_id"]:

        bot_msg = await context.bot.send_message(
            chat_id,
            "⚔️ Нельзя вызвать на дуэль самого себя!",
        )

        schedule_auto_delete(
            context,
            chat_id,
            [bot_msg.message_id],
        )

        return

    opp_title = format_user_title(
        opponent
    )

    if opponent["dick_stolen_today"]:

        bot_msg = await context.bot.send_message(
            chat_id,
            (
                f"💀 <b>{opp_title}</b> сегодня уже "
                f"без хуя. До завтра драться нельзя."
            ),
            parse_mode="HTML",
        )

        schedule_auto_delete(
            context,
            chat_id,
            [bot_msg.message_id],
        )

        return

    if opponent["points"] <= 0:

        bot_msg = await context.bot.send_message(
            chat_id,
            (
                f"⚔️ <b>{opp_title}</b> больше не может "
                f"драться сегодня — у него 0 очков."
            ),
            parse_mode="HTML",
        )

        schedule_auto_delete(
            context,
            chat_id,
            [bot_msg.message_id],
        )

        return

    class SimpleTGUser:

        def __init__(self, uid, uname):
            self.id = uid
            self.username = uname

    opponent_tg = SimpleTGUser(
        opponent["user_id"],
        opponent["username"],
    )

    # Случайно определяем, кто будет атаковать первым.
    # Инициатор дуэли больше не получает автоматического преимущества.
    if random.choice([True, False]):
        first_attacker_tg = initiator_tg
        first_defender_tg = opponent_tg
        first_attacker_data = initiator
        first_defender_data = opponent
    else:
        first_attacker_tg = opponent_tg
        first_defender_tg = initiator_tg
        first_attacker_data = opponent
        first_defender_data = initiator

    await _start_interactive_fight(
        context=context,
        chat_id=chat_id,
        attacker_tg=first_attacker_tg,
        defender_tg=first_defender_tg,
        attacker_data=first_attacker_data,
        defender_data=first_defender_data,
        original_msg_id=original_msg_id,
    )


# ============================================================
# КОМАНДА /duel
# ============================================================

async def duel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if (
        not update.message
        or not update.message.from_user
        or not update.message.chat
    ):
        return

    chat_id = update.message.chat_id

    initiator_tg = update.message.from_user

    target_username = _extract_username(
        update,
        context,
    )

    # --------------------------------------------------------
    # Если соперник не указан — показываем список.
    # --------------------------------------------------------

    if not target_username:

        top_list = get_duel_top(
            chat_id=chat_id,
            limit=20,
        )

        keyboard = []

        for row in top_list:

            username, display_name, _, _, _ = row

            if not username:
                continue

            if (
                initiator_tg.username
                and initiator_tg.username.lower()
                == username.lower()
            ):
                continue

            opponent = get_duel_user_by_username(
                username,
                chat_id,
            )

            if not opponent:
                continue

            if (
                opponent["points"] <= 0
                or opponent["dick_stolen_today"]
            ):
                continue

            clean_label = (
                display_name or username
            ).lstrip("@")

            label = f"⚔️ {clean_label}"

            keyboard.append(
                [
                    InlineKeyboardButton(
                        label,
                        callback_data=f"start_duel_{username}",
                    )
                ]
            )

        if not keyboard:

            await send_and_schedule(
                update,
                context,
                (
                    "❌ В чате нет доступных соперников "
                    "для дуэли (все без очков или без хуев)."
                ),
            )

            return

        reply_markup = InlineKeyboardMarkup(
            keyboard
        )

        await send_and_schedule(
            update,
            context,
            "🗡️ <b>Выберите соперника для дуэли:</b>",
            reply_markup=reply_markup,
        )

        return

    # --------------------------------------------------------
    # Соперник указан напрямую.
    # --------------------------------------------------------

    await _process_duel_fight(
        context,
        initiator_tg,
        target_username,
        chat_id,
        original_msg_id=update.message.message_id,
    )


# ============================================================
# CALLBACK ВЫБОРА СОПЕРНИКА
# ============================================================

async def duel_select_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if (
        not query
        or not query.data
        or not query.data.startswith("start_duel_")
    ):
        return

    target_username = query.data.replace(
        "start_duel_",
        "",
    )

    initiator_tg = query.from_user
    chat_id = update.effective_chat.id

    await query.answer()

    try:
        await query.message.delete()
    except Exception:
        pass

    await _process_duel_fight(
        context,
        initiator_tg,
        target_username,
        chat_id,
    )


# ============================================================
# СТАТИСТИКА
# ============================================================

async def duel_stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if (
        not update.message
        or not update.message.from_user
        or not update.message.chat
    ):
        return

    chat_id = update.message.chat_id

    user = get_or_create_duel_user(
        update.message.from_user,
        chat_id,
    )

    title = format_user_title(user)

    status = (
        "Без хуя 💀"
        if user["dick_stolen_today"]
        else "С хуем 🍆"
    )

    bosses_defeated = get_bosses_defeated(
        user_id=update.message.from_user.id,
        chat_id=chat_id,
    )

    text = (
        f"📊 <b>Статистика дуэлей: {title}</b>\n\n"
        f"Очки: <b>{user['points']} / 100</b>\n"
        f"Побед: <b>{user['wins']}</b>\n"
        f"Поражений: <b>{user['losses']}</b>\n"
        f"Украдено хуев: <b>{user['stolen_dicks_count']}</b>\n"
        f"👹 Побеждено боссов: <b>{bosses_defeated}</b>\n"
        f"Статус на сегодня: <b>{status}</b>"
    )

    await send_and_schedule(
        update,
        context,
        text,
    )


# ============================================================
# ТОП
# ============================================================

async def duel_top_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if (
        not update.message
        or not update.message.chat
    ):
        return

    chat_id = update.message.chat_id

    top = get_duel_top(
        chat_id=chat_id,
        limit=10,
    )

    if not top:

        await send_and_schedule(
            update,
            context,
            "🏆 Таблица лидеров чата пока пуста.",
        )

        return

    sort_label = (
        "очкам"
        if TOP_SORT_BY == "points"
        else "победам"
    )

    text = (
        f"🏆 <b>Топ-10 гномьих дуэлянтов "
        f"чата (по {sort_label}):</b>\n\n"
    )

    for idx, row in enumerate(top, 1):

        username, display_name, wins, losses, points = row

        raw_name = (
            display_name
            or username
            or "Гном"
        )

        clean_name = raw_name.lstrip("@")

        text += (
            f"{idx}. <b>{clean_name}</b> — "
            f"{points} очков "
            f"({wins}W / {losses}L)\n"
        )

    await send_and_schedule(
        update,
        context,
        text,
    )


# ============================================================
# УДАЛЕНИЕ ИГРОКА АДМИНОМ
# ============================================================

async def duel_delete_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if (
        not update.message
        or not update.message.from_user
        or not update.message.chat
    ):
        return

    user_id = update.message.from_user.id

    if user_id not in ADMIN_IDS:

        await send_and_schedule(
            update,
            context,
            "⛔ Недостаточно прав.",
        )

        return

    target_username = _extract_username(
        update,
        context,
    )

    if not target_username:

        await send_and_schedule(
            update,
            context,
            (
                "⚠️ Укажите ник: "
                "<code>/duel_delete username</code>"
            ),
        )

        return

    chat_id = update.message.chat_id

    deleted = delete_duel_user_by_username(
        target_username,
        chat_id,
    )

    clean_target = target_username.lstrip("@")

    if deleted:

        await send_and_schedule(
            update,
            context,
            (
                f"✅ Пользователь {clean_target} "
                f"удален из базы дуэлей этого чата."
            ),
        )

    else:

        await send_and_schedule(
            update,
            context,
            (
                f"❌ Пользователь {clean_target} "
                f"не найден в базе этого чата."
            ),
        )


# ============================================================
# БОССЫ
# ============================================================

BOSS_PHASE_TIMEOUT = 10
BOSS_ROUND_PAUSE = 5
BOSS_REQUIRED_HITS = 5

BOSS_REG_CUTOFF_HOUR = 18
BOSS_REG_CUTOFF_MINUTE = 0
BOSS_JOIN_TIMEOUT = 30

BOSS_ZONE_NAMES = {
    "head": "Голова",
    "body": "Торс",
    "dick": "Хуй",
}

BOSS_ZONES = ("head", "body", "dick")

ACTIVE_BOSS_BATTLES = {}

_BOSS_REG_DB_PATH = (
    Path(__file__).resolve().parent.parent / "bot_database.db"
)

_BOSS_REG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS boss_registrations (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT,
    first_name TEXT NOT NULL,
    last_name TEXT,
    reg_date TEXT NOT NULL,
    PRIMARY KEY (chat_id, user_id, reg_date)
)
"""


def _boss_reg_timezone():
    try:
        return ZoneInfo(DUEL_TIMEZONE)
    except Exception:
        logging.exception(
            "Не удалось загрузить DUEL_TIMEZONE=%r для регистрации босса",
            DUEL_TIMEZONE,
        )
        return ZoneInfo("UTC")


def _boss_today():
    return datetime.now(_boss_reg_timezone()).date().isoformat()


def _boss_registration_is_open():
    now = datetime.now(_boss_reg_timezone())
    cutoff = dt_time(
        BOSS_REG_CUTOFF_HOUR,
        BOSS_REG_CUTOFF_MINUTE,
    )
    return now.time() < cutoff


def _boss_registration_connect():
    conn = sqlite3.connect(
        str(_BOSS_REG_DB_PATH),
        timeout=10,
    )
    conn.execute(_BOSS_REG_TABLE_SQL)
    conn.commit()
    return conn


def _boss_register_user(chat_id, tg_user):
    reg_date = _boss_today()

    with _boss_registration_connect() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO boss_registrations
            (
                chat_id,
                user_id,
                username,
                first_name,
                last_name,
                reg_date
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                tg_user.id,
                tg_user.username,
                tg_user.first_name or "",
                tg_user.last_name,
                reg_date,
            ),
        )

        return cursor.rowcount > 0


def _boss_get_registered_users(chat_id):
    reg_date = _boss_today()

    with _boss_registration_connect() as conn:
        rows = conn.execute(
            """
            SELECT
                user_id,
                username,
                first_name,
                last_name
            FROM boss_registrations
            WHERE chat_id = ?
              AND reg_date = ?
            ORDER BY rowid
            """,
            (chat_id, reg_date),
        ).fetchall()

    return rows


def _boss_clear_registrations(chat_id, reg_date=None):
    reg_date = reg_date or _boss_today()

    with _boss_registration_connect() as conn:
        conn.execute(
            """
            DELETE FROM boss_registrations
            WHERE chat_id = ?
              AND reg_date = ?
            """,
            (chat_id, reg_date),
        )
        conn.commit()


def _boss_get_registered_chat_ids(reg_date=None):
    reg_date = reg_date or _boss_today()

    with _boss_registration_connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT chat_id
            FROM boss_registrations
            WHERE reg_date = ?
            """,
            (reg_date,),
        ).fetchall()

    return {row[0] for row in rows}


# ------------------------------------------------------------
# КЛАВИАТУРЫ
# ------------------------------------------------------------

def _boss_attack_keyboard(round_num: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⚔️ Голова",
                callback_data=f"boss_attack_head_{round_num}",
            ),
            InlineKeyboardButton(
                "⚔️ Торс",
                callback_data=f"boss_attack_body_{round_num}",
            ),
            InlineKeyboardButton(
                "⚔️ Хуй",
                callback_data=f"boss_attack_dick_{round_num}",
            ),
        ]
    ])


def _boss_block_keyboard(round_num: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🛡 Голова",
                callback_data=f"boss_block_head_{round_num}",
            ),
            InlineKeyboardButton(
                "🛡 Торс",
                callback_data=f"boss_block_body_{round_num}",
            ),
            InlineKeyboardButton(
                "🛡 Хуй",
                callback_data=f"boss_block_dick_{round_num}",
            ),
        ]
    ])


# ------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ------------------------------------------------------------

def _boss_alive_players(battle):
    return [
        participant
        for participant in battle["participants"].values()
        if participant["alive"]
    ]


def _boss_player_title(participant):
    return format_user_title(participant["data"])


def _boss_all_alive_chosen(battle, field):
    alive = _boss_alive_players(battle)

    if not alive:
        return False

    return all(
        participant.get(field) is not None
        for participant in alive
    )


def _boss_phase_status(participant, phase):
    if not participant["alive"]:
        return "💀 погиб"

    if phase == "attack":
        return (
            "🟢 выбрал"
            if participant.get("attack") is not None
            else "🟡 выбирает"
        )

    if phase == "block":
        return (
            "🟢 выбрал"
            if participant.get("block") is not None
            else "🟡 выбирает"
        )

    return ""


def _boss_players_status_text(battle):
    lines = []

    for participant in battle["participants"].values():
        title = _boss_player_title(participant)
        status = _boss_phase_status(
            participant,
            battle["phase"],
        )

        lines.append(
            f"• <b>{title}</b> — {status}"
        )

    return "\n".join(lines)


def _boss_phase_text(battle):
    boss = battle["boss"]

    alive_count = len(_boss_alive_players(battle))
    total_count = len(battle["participants"])

    if battle["phase"] == "attack":
        return (
            f"💀 <b>{boss['name']} — РАУНД {battle['round']}</b>\n\n"
            f"⚔️ <b>ФАЗА АТАКИ</b>\n"
            f"Каждый живой игрок выбирает, куда ударить босса.\n\n"
            f"🎯 Урон боссу: "
            f"<b>{battle['hits']} / {BOSS_REQUIRED_HITS}</b>\n"
            f"👥 В живых: <b>{alive_count} / {total_count}</b>\n\n"
            f"<b>Игроки:</b>\n"
            f"{_boss_players_status_text(battle)}\n\n"
            f"⚔️ Выберите зону атаки:"
        )

    return (
        f"💀 <b>{boss['name']} — РАУНД {battle['round']}</b>\n\n"
        f"🛡 <b>ФАЗА ЗАЩИТЫ</b>\n"
        f"Босс сейчас атакует. Каждый живой игрок "
        f"выбирает, какую зону защищать.\n\n"
        f"🎯 Урон боссу: "
        f"<b>{battle['hits']} / {BOSS_REQUIRED_HITS}</b>\n"
        f"👥 В живых: <b>{alive_count} / {total_count}</b>\n\n"
        f"<b>Игроки:</b>\n"
        f"{_boss_players_status_text(battle)}\n\n"
        f"🛡 Выберите зону защиты:"
    )


async def _boss_render_phase(context, chat_id):
    battle = ACTIVE_BOSS_BATTLES.get(chat_id)

    if not battle:
        return

    text = _boss_phase_text(battle)

    if battle["phase"] == "attack":
        keyboard = _boss_attack_keyboard(
            battle["round"]
        )
    else:
        keyboard = _boss_block_keyboard(
            battle["round"]
        )

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=battle["message_id"],
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception:
        logging.exception(
            "Не удалось обновить фазу битвы с боссом "
            "в чате %s",
            chat_id,
        )


def _boss_cancel_timer(battle):
    task = battle.get("phase_task")
    battle["phase_task"] = None

    if not task or task.done():
        return

    if task is asyncio.current_task():
        return

    task.cancel()


def _boss_auto_zone():
    return random.choice(BOSS_ZONES)


async def _boss_auto_choose_for_zazevasha(
    context,
    chat_id,
    battle,
    participant,
    phase,
):
    if not participant["alive"]:
        return

    title = _boss_player_title(participant)
    zone = _boss_auto_zone()

    if phase == "attack":
        if participant.get("attack") is not None:
            return

        participant["attack"] = zone
        action_text = (
            f"⚔️ <b>{title}</b> зазевался. "
            f"Нож сам пошёл в <b>{BOSS_ZONE_NAMES[zone]}</b>."
        )
    else:
        if participant.get("block") is not None:
            return

        participant["block"] = zone
        action_text = (
            f"🛡 <b>{title}</b> зазевался. "
            f"Рука сама прикрыла <b>{BOSS_ZONE_NAMES[zone]}</b>."
        )

    try:
        timeout_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=action_text,
            parse_mode="HTML",
        )
        schedule_auto_delete(
            context,
            chat_id,
            [timeout_msg.message_id],
        )
    except Exception:
        logging.exception(
            "Не удалось отправить сообщение автодействия босса "
            "в чат %s",
            chat_id,
        )


# ------------------------------------------------------------
# НАЧАЛО НОВОГО РАУНДА
# ------------------------------------------------------------

async def _boss_start_round(
    context,
    chat_id,
):
    battle = ACTIVE_BOSS_BATTLES.get(chat_id)

    if not battle:
        return

    alive = _boss_alive_players(battle)

    if not alive:
        await _boss_finish_defeat(
            context,
            chat_id,
        )
        return

    battle["round"] += 1
    battle["phase"] = "attack"

    battle["boss_attack"] = random.choice(
        BOSS_ZONES
    )

    battle["boss_block"] = random.choice(
        BOSS_ZONES
    )

    for participant in battle["participants"].values():
        participant["attack"] = None
        participant["block"] = None

    await _boss_render_phase(
        context,
        chat_id,
    )

    _boss_cancel_timer(battle)

    battle["phase_task"] = asyncio.create_task(
        _boss_phase_timer(
            context,
            chat_id,
            battle["round"],
            "attack",
        )
    )


# ------------------------------------------------------------
# ТАЙМЕР ФАЗЫ
# ------------------------------------------------------------

async def _boss_phase_timer(
    context,
    chat_id,
    round_num,
    phase,
):
    current_task = asyncio.current_task()

    try:
        await asyncio.sleep(BOSS_PHASE_TIMEOUT)
    except asyncio.CancelledError:
        return

    battle = ACTIVE_BOSS_BATTLES.get(chat_id)

    if not battle:
        return

    finish_defeat = False
    switch_to_block = False
    resolve_round = False

    async with battle["lock"]:
        # Защита от старых/дублирующихся таймеров.
        # Если callback уже заменил phase_task, этот таймер больше
        # не имеет права двигать бой дальше.
        if battle.get("phase_task") is not current_task:
            return

        if (
            battle["round"] != round_num
            or battle["phase"] != phase
        ):
            return

        alive = _boss_alive_players(battle)

        if not alive:
            finish_defeat = True
            battle["phase_task"] = None
        else:
            # Если кто-то зазевался, делаем ему случайный ход.
            for participant in alive:
                field = "attack" if phase == "attack" else "block"

                if participant.get(field) is None:
                    await _boss_auto_choose_for_zazevasha(
                        context,
                        chat_id,
                        battle,
                        participant,
                        phase,
                    )

            if phase == "attack":
                battle["phase"] = "block"
                switch_to_block = True
                battle["phase_task"] = None

            elif phase == "block":
                resolve_round = True
                battle["phase_task"] = None

    if finish_defeat:
        await _boss_finish_defeat(
            context,
            chat_id,
        )
        return

    if switch_to_block:
        current_battle = ACTIVE_BOSS_BATTLES.get(chat_id)

        if not current_battle:
            return

        await _boss_render_phase(
            context,
            chat_id,
        )

        current_battle = ACTIVE_BOSS_BATTLES.get(chat_id)

        if not current_battle:
            return

        async with current_battle["lock"]:
            if (
                current_battle["round"] != round_num
                or current_battle["phase"] != "block"
            ):
                return

            current_battle["phase_task"] = asyncio.create_task(
                _boss_phase_timer(
                    context,
                    chat_id,
                    round_num,
                    "block",
                )
            )

        return

    if resolve_round:
        await _boss_resolve_round(
            context,
            chat_id,
        )


# ------------------------------------------------------------
# CALLBACK БОССА
# ------------------------------------------------------------

async def boss_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not query or not query.data:
        return

    chat_id = update.effective_chat.id

    battle = ACTIVE_BOSS_BATTLES.get(chat_id)

    if not battle:
        await query.answer(
            "Битва уже закончилась.",
            show_alert=True,
        )
        return

    async with battle["lock"]:
        callback_data = query.data
        user_id = query.from_user.id

        if callback_data == "boss_join":
            if battle["phase"] != "join":
                await query.answer(
                    "Битва уже началась.",
                    show_alert=True,
                )
                return

            if user_id in battle["participants"]:
                await query.answer(
                    "Ты уже участвуешь.",
                    show_alert=True,
                )
                return

            user_data = get_or_create_duel_user(
                query.from_user,
                chat_id,
            )

            battle["participants"][user_id] = {
                "tg_user": query.from_user,
                "data": user_data,
                "attack": None,
                "block": None,
                "alive": True,
                "hits": 0,
                "misses": 0,
                "blocks": 0,
                "rounds_survived": 0,
                "death_round": None,
                "death_by_zone": None,
                "death_defended_zone": None,
                "death_attack_zone": None,
            }

            await query.answer(
                "Ты вступил в битву! ⚔️"
            )

            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=battle["message_id"],
                    text=(
                        f"💀 <b>{battle['boss']['name']}</b>\n\n"
                        f"👹 Босс готов к битве!\n\n"
                        f"👥 Участников: "
                        f"<b>{len(battle['participants'])}</b>\n\n"
                        f"⚔️ Присоединяйтесь к бойне."
                    ),
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(
                                "⚔️ Присоединиться",
                                callback_data="boss_join",
                            )
                        ]
                    ]),
                )
            except Exception:
                pass

            return

        if callback_data.startswith("boss_attack_"):
            if battle["phase"] != "attack":
                await query.answer(
                    "Сейчас фаза защиты.",
                    show_alert=True,
                )
                return

            participant = battle["participants"].get(
                user_id
            )

            if not participant:
                await query.answer(
                    "Ты не участвуешь в битве.",
                    show_alert=True,
                )
                return

            if not participant["alive"]:
                await query.answer(
                    "Ты уже погиб.",
                    show_alert=True,
                )
                return

            parts = callback_data.split("_")

            if len(parts) != 4:
                await query.answer(
                    "Устаревшая кнопка.",
                    show_alert=True,
                )
                return

            zone = parts[2]

            try:
                button_round = int(parts[3])
            except ValueError:
                await query.answer(
                    "Устаревшая кнопка.",
                    show_alert=True,
                )
                return

            if button_round != battle["round"]:
                await query.answer(
                    "Этот раунд уже закончился.",
                    show_alert=True,
                )
                return

            if zone not in BOSS_ZONES:
                await query.answer(
                    "Неизвестная зона.",
                    show_alert=True,
                )
                return

            participant["attack"] = zone

            await query.answer(
                f"Атака: {BOSS_ZONE_NAMES[zone]} ⚔️"
            )

            await _boss_render_phase(
                context,
                chat_id,
            )

            if _boss_all_alive_chosen(
                battle,
                "attack",
            ):
                _boss_cancel_timer(battle)

                battle["phase"] = "block"

                for player in battle["participants"].values():
                    if player["alive"]:
                        player["block"] = None

                await _boss_render_phase(
                    context,
                    chat_id,
                )

                battle["phase_task"] = asyncio.create_task(
                    _boss_phase_timer(
                        context,
                        chat_id,
                        battle["round"],
                        "block",
                    )
                )

            return

        if callback_data.startswith("boss_block_"):
            if battle["phase"] != "block":
                await query.answer(
                    "Сначала все должны выбрать атаку.",
                    show_alert=True,
                )
                return

            participant = battle["participants"].get(
                user_id
            )

            if not participant:
                await query.answer(
                    "Ты не участвуешь в битве.",
                    show_alert=True,
                )
                return

            if not participant["alive"]:
                await query.answer(
                    "Ты уже погиб.",
                    show_alert=True,
                )
                return

            parts = callback_data.split("_")

            if len(parts) != 4:
                await query.answer(
                    "Устаревшая кнопка.",
                    show_alert=True,
                )
                return

            zone = parts[2]

            try:
                button_round = int(parts[3])
            except ValueError:
                await query.answer(
                    "Устаревшая кнопка.",
                    show_alert=True,
                )
                return

            if button_round != battle["round"]:
                await query.answer(
                    "Этот раунд уже закончился.",
                    show_alert=True,
                )
                return

            if zone not in BOSS_ZONES:
                await query.answer(
                    "Неизвестная зона.",
                    show_alert=True,
                )
                return

            participant["block"] = zone

            await query.answer(
                f"Защита: {BOSS_ZONE_NAMES[zone]} 🛡"
            )

            await _boss_render_phase(
                context,
                chat_id,
            )

            should_resolve = _boss_all_alive_chosen(
                battle,
                "block",
            )

            if should_resolve:
                _boss_cancel_timer(battle)

                # Нельзя await-ить _boss_resolve_round здесь:
                # callback сам ещё держит battle["lock"], а
                # _boss_resolve_round пытается взять тот же lock.
                #
                # Создаём задачу сейчас — она начнёт выполняться
                # после выхода callback из async with.
                asyncio.create_task(
                    _boss_resolve_round(
                        context,
                        chat_id,
                    )
                )

            return


# ------------------------------------------------------------
# РЕЗУЛЬТАТ РАУНДА
# ------------------------------------------------------------

async def _boss_resolve_round(
    context,
    chat_id,
):
    battle = ACTIVE_BOSS_BATTLES.get(chat_id)

    if not battle:
        return

    async with battle["lock"]:
        # Пока держим lock, только рассчитываем и сохраняем состояние.
        # Telegram API, sleep и финализацию выполняем после выхода из lock.
        if battle["phase"] != "block":
            return

        # Сразу переводим раунд в resolving после расчёта ниже.
        # Это не даёт второму callback/таймеру разрешить тот же раунд.
        boss_attack = battle["boss_attack"]
        boss_block = battle["boss_block"]

        results = []

        for participant in battle["participants"].values():
            if not participant["alive"]:
                continue

            attack = participant.get("attack")
            block = participant.get("block")

            # Защита от старого/битого таймера: зазевавшемуся
            # участнику всё равно назначаем ход.
            if attack not in BOSS_ZONES:
                attack = _boss_auto_zone()
                participant["attack"] = attack

            if block not in BOSS_ZONES:
                block = _boss_auto_zone()
                participant["block"] = block

            hit = attack != boss_block

            if hit:
                battle["hits"] += 1
                participant["hits"] += 1
                attack_result = "💥 ПОПАДАНИЕ"
            else:
                participant["misses"] += 1
                attack_result = "💨 ПРОМАХ"

            survived = block == boss_attack

            if survived:
                participant["blocks"] += 1
                participant["rounds_survived"] += 1
                block_result = "🛡 ЗАБЛОКИРОВАЛ"
            else:
                block_result = "💀 УБИТ"
                participant["alive"] = False
                participant["death_round"] = battle["round"]
                participant["death_by_zone"] = boss_attack
                participant["death_defended_zone"] = block
                participant["death_attack_zone"] = attack

            title = _boss_player_title(participant)

            results.append(
                f"<b>{title}</b>\n"
                f"⚔️ {BOSS_ZONE_NAMES[attack]} → "
                f"{attack_result}\n"
                f"🛡 {BOSS_ZONE_NAMES[block]} → "
                f"{block_result}"
            )

        alive_after = len(_boss_alive_players(battle))

        text = (
            f"💥 <b>РАУНД {battle['round']} — РЕЗУЛЬТАТ</b>\n\n"
            f"👹 Босс атаковал: "
            f"<b>{BOSS_ZONE_NAMES[boss_attack]}</b>\n"
            f"🛡 Босс защищал: "
            f"<b>{BOSS_ZONE_NAMES[boss_block]}</b>\n\n"
            + "\n\n".join(results)
            + "\n\n"
            f"🎯 Урон боссу: "
            f"<b>{battle['hits']} / {BOSS_REQUIRED_HITS}</b>\n"
            f"👥 В живых: "
            f"<b>{alive_after}</b> / "
            f"<b>{len(battle['participants'])}</b>"
        )

        victory = battle["hits"] >= BOSS_REQUIRED_HITS
        defeat = alive_after == 0

        # Помечаем раунд завершённым. Это не даёт второму callback
        # или таймеру запустить его повторно.
        battle["phase"] = "resolving"

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=battle["message_id"],
            text=text,
            parse_mode="HTML",
        )
    except Exception:
        logging.exception(
            "Не удалось показать результат раунда босса "
            "в чате %s",
            chat_id,
        )

    if victory:
        await asyncio.sleep(2)
        await _boss_finish_victory(
            context,
            chat_id,
        )
        return

    if defeat:
        await asyncio.sleep(2)
        await _boss_finish_defeat(
            context,
            chat_id,
        )
        return

    await asyncio.sleep(BOSS_ROUND_PAUSE)

    current_battle = ACTIVE_BOSS_BATTLES.get(chat_id)

    if not current_battle:
        return

    await _boss_start_round(
        context,
        chat_id,
    )


# ------------------------------------------------------------
# ФИНАЛЬНАЯ СТАТИСТИКА БИТВЫ
# ------------------------------------------------------------

def _plural_rounds(value):
    value = int(value)

    if value % 10 == 1 and value % 100 != 11:
        return "раунд"
    if 2 <= value % 10 <= 4 and not 12 <= value % 100 <= 14:
        return "раунда"
    return "раундов"


def _boss_death_epitaph(participant, boss_name):
    title = _boss_player_title(participant)
    attack_zone = BOSS_ZONE_NAMES.get(
        participant.get("death_attack_zone"),
        "неизвестную зону",
    )
    death_zone = BOSS_ZONE_NAMES.get(
        participant.get("death_by_zone"),
        "неизвестную зону",
    )
    defended_zone = BOSS_ZONE_NAMES.get(
        participant.get("death_defended_zone"),
        "неизвестную зону",
    )
    round_num = participant.get("death_round") or "последнем"

    phrases = [
        (
            f"💀 <b>{title}</b> пал в раунде <b>{round_num}</b>. "
            f"Бил в <b>{attack_zone}</b>, защищал <b>{defended_zone}</b>, "
            f"а <b>{boss_name}</b> пришёл в <b>{death_zone}</b>. "
            f"Гномская разведка считает это смелостью. "
            f"Гномская бухгалтерия — ошибкой."
        ),
        (
            f"☠️ <b>{title}</b> держался до раунда <b>{round_num}</b>, "
            f"после чего <b>{boss_name}</b> объяснил разницу между "
            f"«я защищаюсь» и «я угадал не туда». "
            f"Удар пришёл в <b>{death_zone}</b>, "
            f"блок стоял в <b>{defended_zone}</b>."
        ),
        (
            f"🪦 Здесь мог бы стоять памятник <b>{title}</b>. "
            f"Он бил в <b>{attack_zone}</b>, прикрывал "
            f"<b>{defended_zone}</b> и в раунде <b>{round_num}</b> "
            f"получил от босса в <b>{death_zone}</b>. "
            f"Памятник решили не ставить: металл нужен для новых ножей."
        ),
        (
            f"💀 <b>{title}</b> совершил тактическое отступление "
            f"прямо в могилу. Произошло это в раунде <b>{round_num}</b>: "
            f"атака — <b>{attack_zone}</b>, защита — <b>{defended_zone}</b>, "
            f"босс — в <b>{death_zone}</b>. Совпадение? Нет. Судьба."
        ),
    ]

    return random.choice(phrases)


def _boss_survivor_epitaph(participant):
    title = _boss_player_title(participant)
    hits = participant.get("hits", 0)
    misses = participant.get("misses", 0)
    blocks = participant.get("blocks", 0)
    survived = participant.get("rounds_survived", 0)

    if hits >= 2 and blocks >= 2:
        phrase = "рубился как настоящий гномий терминатор"
    elif hits >= 2:
        phrase = "превратил босса в тренировочную мишень"
    elif blocks >= 2:
        phrase = "оказался подозрительно хорош в умении не умереть"
    elif hits:
        phrase = "хотя бы успел оставить на боссе несколько зарубок"
    else:
        phrase = "выжил почти исключительно благодаря наглости"

    return (
        f"🛡 <b>{title}</b> — выжил. {phrase}. "
        f"Попаданий: <b>{hits}</b>, промахов: <b>{misses}</b>, "
        f"блоков: <b>{blocks}</b>, пережито раундов: "
        f"<b>{survived}</b>."
    )


def _boss_battle_hero(participants):
    alive = [p for p in participants if p["alive"]]

    if not participants:
        return None

    return max(
        participants,
        key=lambda p: (
            p.get("hits", 0),
            p.get("blocks", 0),
            p.get("rounds_survived", 0),
            1 if p in alive else 0,
        ),
    )


def _boss_final_report(battle, victory: bool):
    participants = list(battle["participants"].values())
    boss_name = battle["boss"]["name"]
    total = len(participants)
    survivors = [
        p for p in participants
        if p["alive"]
    ]
    dead = [
        p for p in participants
        if not p["alive"]
    ]
    hero = _boss_battle_hero(participants)

    lines = []

    if victory:
        lines.extend([
            "🏆 <b>ЛЕГЕНДА БИТВЫ</b>",
            "",
            f"👹 <b>{boss_name}</b> пал после "
            f"<b>{battle['hits']}</b> попаданий.",
            f"⚔️ Продолжительность: <b>{battle['round']}</b> "
            f"{_plural_rounds(battle['round'])}.",
            f"👥 Отряд: <b>{total}</b> — выжило "
            f"<b>{len(survivors)}</b>, погибло <b>{len(dead)}</b>.",
            "",
            "🛡 <b>ВЫЖИВШИЕ:</b>",
        ])

        lines.extend(
            _boss_survivor_epitaph(p)
            for p in survivors
        )

        if dead:
            lines.extend([
                "",
                "💀 <b>ПАВШИЕ ГЕРОИ:</b>",
            ])
            lines.extend(
                _boss_death_epitaph(p, boss_name)
                for p in dead
            )

        if hero:
            hero_title = _boss_player_title(hero)
            lines.extend([
                "",
                f"👑 <b>ГЕРОЙ БИТВЫ: {hero_title}</b>",
                f"Нанёс <b>{hero.get('hits', 0)}</b> попаданий, "
                f"сделал <b>{hero.get('blocks', 0)}</b> блоков "
                f"и пережил <b>{hero.get('rounds_survived', 0)}</b> "
                f"{_plural_rounds(hero.get('rounds_survived', 0))}.",
            ])

        lines.extend([
            "",
            "💯 <b>Награда:</b> всем выжившим установлено 100 очков.",
            "🍆 Украденный сегодня хуй возвращён.",
            "",
            "👑 <b>Великий бог хуекрадов постановил:</b> "
            "сегодня эти гномы официально слишком охуенны, чтобы умереть.",
        ])

    else:
        lines.extend([
            "💀 <b>ПОСМЕРТНАЯ ЛЕТОПИСЬ ОТРЯДА</b>",
            "",
            f"👹 <b>{boss_name}</b> остался стоять.",
            f"🎯 Гномы нанесли <b>{battle['hits']}</b> из "
            f"<b>{BOSS_REQUIRED_HITS}</b> нужных попаданий.",
            f"⚔️ Отряд продержался <b>{battle['round']}</b> "
            f"{_plural_rounds(battle['round'])}.",
            f"👥 Участников: <b>{total}</b>. Выжили: <b>0</b>.",
            "",
            "💀 <b>КАК ВСЕ УМЕРЛИ:</b>",
        ])

        lines.extend(
            _boss_death_epitaph(p, boss_name)
            for p in dead
        )

        if hero:
            hero_title = _boss_player_title(hero)
            lines.extend([
                "",
                f"🩸 <b>ПОСЛЕДНИЙ НАСТОЯЩИЙ ГНОМ: {hero_title}</b>",
                f"На его счету <b>{hero.get('hits', 0)}</b> попаданий "
                f"и <b>{hero.get('blocks', 0)}</b> блоков. "
                "Умер, но статистику уже не отнять.",
            ])

        lines.extend([
            "",
            "📜 <b>Вердикт:</b> гномы были храбрыми. "
            "Но босс был охуенно внимательным.",
        ])

    return "\n".join(lines)


async def _boss_send_final_report(
    context,
    chat_id,
    battle,
    victory,
):
    try:
        text = _boss_final_report(
            battle,
            victory,
        )
    except Exception:
        logging.exception(
            "Ошибка формирования финального отчёта босса "
            "в чате %s",
            chat_id,
        )

        # Финальный отчёт не должен исчезать из-за одной ошибки
        # в красивой статистике.
        text = (
            "💀 <b>БИТВА ОКОНЧЕНА</b>\\n\\n"
            "Босс больше не сражается. "
            "Гномская летопись почему-то отказалась "
            "писать подробности."
        )

    chunks = []
    current = ""

    for paragraph in text.split("\n\n"):
        candidate = (
            paragraph
            if not current
            else current + "\n\n" + paragraph
        )

        if len(candidate) <= 3900:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        while len(paragraph) > 3900:
            chunks.append(paragraph[:3900])
            paragraph = paragraph[3900:]

        current = paragraph

    if current:
        chunks.append(current)

    if not chunks:
        chunks = [text]

    first_message_id = battle.get("message_id")

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=first_message_id,
            text=chunks[0],
            parse_mode="HTML",
        )
    except Exception:
        logging.exception(
            "Не удалось отредактировать финальное сообщение "
            "босса в чате %s",
            chat_id,
        )

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=chunks[0],
                parse_mode="HTML",
            )
        except Exception:
            logging.exception(
                "Не удалось отправить финальный отчёт босса "
                "в чат %s",
                chat_id,
            )

    for chunk in chunks[1:]:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode="HTML",
            )
        except Exception:
            logging.exception(
                "Не удалось отправить часть финального отчёта "
                "босса в чат %s",
                chat_id,
            )
            break


# ------------------------------------------------------------
# ПОБЕДА
# ------------------------------------------------------------

async def _boss_finish_victory(
    context,
    chat_id,
):
    battle = ACTIVE_BOSS_BATTLES.pop(
        chat_id,
        None,
    )

    if not battle:
        return

    _boss_cancel_timer(battle)

    for participant in battle["participants"].values():
        if not participant["alive"]:
            continue

        user_id = participant["tg_user"].id

        try:
            reward_boss_victory(
                user_id=user_id,
                chat_id=chat_id,
            )
        except Exception:
            logging.exception(
                "Ошибка награды за победу над боссом"
            )

    try:
        await _boss_send_final_report(
            context,
            chat_id,
            battle,
            victory=True,
        )
    except Exception:
        logging.exception(
            "Критическая ошибка финализации победы босса "
            "в чате %s",
            chat_id,
        )


# ------------------------------------------------------------
# ПОРАЖЕНИЕ
# ------------------------------------------------------------

async def _boss_finish_defeat(
    context,
    chat_id,
):
    battle = ACTIVE_BOSS_BATTLES.pop(
        chat_id,
        None,
    )

    if not battle:
        return

    _boss_cancel_timer(battle)

    try:
        await _boss_send_final_report(
            context,
            chat_id,
            battle,
            victory=False,
        )
    except Exception:
        logging.exception(
            "Критическая ошибка финализации поражения босса "
            "в чате %s",
            chat_id,
        )


# ------------------------------------------------------------
# СОЗДАНИЕ БОЕВОГО УЧАСТНИКА
# ------------------------------------------------------------

def _boss_make_participant(
    tg_user,
    chat_id,
):
    user_data = get_or_create_duel_user(
        tg_user,
        chat_id,
    )

    return {
        "tg_user": tg_user,
        "data": user_data,
        "attack": None,
        "block": None,
        "alive": True,
        "hits": 0,
        "misses": 0,
        "blocks": 0,
        "rounds_survived": 0,
        "death_round": None,
        "death_by_zone": None,
        "death_defended_zone": None,
        "death_attack_zone": None,
    }


def _boss_tg_user_from_registration(row):
    user_id, username, first_name, last_name = row

    # telegram.User достаточно для существующей функции
    # get_or_create_duel_user.
    from telegram import User

    return User(
        id=int(user_id),
        first_name=first_name or "",
        is_bot=False,
        last_name=last_name,
        username=username,
    )


# ------------------------------------------------------------
# ЗАПУСК БИТВЫ С БОССОМ
# ------------------------------------------------------------

async def _start_boss_battle(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    include_registrations=False,
):
    """
    Запускает набор участников на битву с боссом.

    При ежедневном запуске в 18:00 include_registrations=True:
    все записавшиеся через /boss_reg автоматически становятся
    участниками, как если бы они сами вступили в набор.
    """
    if chat_id in ACTIVE_BOSS_BATTLES:
        return False

    registered_rows = (
        _boss_get_registered_users(chat_id)
        if include_registrations
        else []
    )

    boss = random.choice(BOSSES)

    bot_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"💀 <b>{boss['name']}</b>\n\n"
            f"👹 В чат явился босс!\n\n"
            f"🎯 Его нужно поразить "
            f"<b>{BOSS_REQUIRED_HITS} раз</b>.\n"
            f"💀 Босс убивает с одного удара, "
            f"если игрок не заблокировал нужную зону.\n\n"
            f"⚔️ Нажимайте кнопку ниже, "
            f"чтобы присоединиться."
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⚔️ Присоединиться",
                    callback_data="boss_join",
                )
            ]
        ]),
    )

    battle = {
        "boss": boss,
        "participants": {},
        "hits": 0,
        "round": 0,
        "phase": "join",
        "message_id": bot_msg.message_id,
        "phase_task": None,
        "lock": asyncio.Lock(),
        "boss_attack": None,
        "boss_block": None,
    }

    for row in registered_rows:
        tg_user = _boss_tg_user_from_registration(row)

        if tg_user.id in battle["participants"]:
            continue

        try:
            battle["participants"][tg_user.id] = _boss_make_participant(
                tg_user,
                chat_id,
            )
        except Exception:
            logging.exception(
                "Не удалось добавить предварительно "
                "зарегистрированного участника %s в чате %s",
                tg_user.id,
                chat_id,
            )

    ACTIVE_BOSS_BATTLES[chat_id] = battle

    if battle["participants"]:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=battle["message_id"],
                text=(
                    f"💀 <b>{boss['name']}</b>\n\n"
                    f"👹 Босс явился в подземелье!\n\n"
                    f"⚔️ Заранее записались: "
                    f"<b>{len(battle['participants'])}</b>\n\n"
                    f"Другие храбрецы ещё могут вступить в бой."
                ),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⚔️ Присоединиться",
                            callback_data="boss_join",
                        )
                    ]
                ]),
            )
        except Exception:
            pass

    battle["phase_task"] = asyncio.create_task(
        _boss_join_timer(
            context,
            chat_id,
        )
    )

    return True


# ------------------------------------------------------------
# РЕГИСТРАЦИЯ /boss_reg
# ------------------------------------------------------------

async def boss_reg_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if (
        not update.message
        or not update.message.from_user
        or not update.message.chat
    ):
        return

    chat = update.message.chat

    if chat.type not in {"group", "supergroup"}:
        await send_and_schedule(
            update,
            context,
            "⚔️ Записываться на гномью бойню можно только в группе.",
        )
        return

    chat_id = chat.id

    if not _boss_registration_is_open():
        await send_and_schedule(
            update,
            context,
            "⏰ Запись на сегодняшнюю битву уже закрыта. "
            "В 18:00 увидимся на арене.",
        )
        return

    if chat_id in ACTIVE_BOSS_BATTLES:
        await send_and_schedule(
            update,
            context,
            "⚔️ Битва уже идёт. На неё запись закрыта.",
        )
        return

    # Команда участника также означает, что бот должен считать
    # этот чат активным для ежедневного босса.
    set_boss_enabled(chat_id, True)

    added = _boss_register_user(
        chat_id,
        update.message.from_user,
    )

    if added:
        await send_and_schedule(
            update,
            context,
            (
                "⚔️ <b>Гном записан на сегодняшнюю бойню.</b>\n\n"
                "В 18:00 твоя борода сама окажется на арене. "
                "Нож бери с собой."
            ),
            parse_mode="HTML",
        )
    else:
        await send_and_schedule(
            update,
            context,
            (
                "🍺 Ты уже записан на сегодняшнюю бойню.\n\n"
                "В 18:00 просто приходи рубиться."
            ),
            parse_mode="HTML",
        )


# ------------------------------------------------------------
# РУЧНОЙ ЗАПУСК /boss
# ------------------------------------------------------------

async def boss_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if (
        not update.message
        or not update.message.from_user
        or not update.message.chat
    ):
        return

    if update.message.from_user.id not in ADMIN_IDS:
        await send_and_schedule(
            update,
            context,
            "⛔ Недостаточно прав.",
        )
        return

    chat_id = update.message.chat_id

    if chat_id > 0:
        await send_and_schedule(
            update,
            context,
            "👹 Босс запускается только в групповом чате.",
        )
        return

    if chat_id in ACTIVE_BOSS_BATTLES:
        await send_and_schedule(
            update,
            context,
            "👹 В этом чате уже идет битва с боссом.",
        )
        return

    set_boss_enabled(chat_id, True)

    try:
        started = await _start_boss_battle(
            context,
            chat_id,
            include_registrations=False,
        )
    except (BadRequest, Forbidden) as exc:
        set_boss_enabled(chat_id, False)
        logging.warning(
            "Не удалось вручную запустить босса в чате %s: %s",
            chat_id,
            exc,
        )
        return

    if started:
        return


# ------------------------------------------------------------
# ЕЖЕДНЕВНЫЙ БОСС
# ------------------------------------------------------------

async def boss_daily_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Ежедневно запускает битву в 18:00.

    Все пользователи, записавшиеся через /boss_reg до 18:00,
    автоматически становятся участниками. Остальные могут
    присоединиться через кнопку в течение окна набора.
    """
    chats = set(get_all_chats())
    chats.update(_boss_get_registered_chat_ids())

    started = 0
    skipped = 0
    disabled = 0

    for chat_id in chats:
        if chat_id in ACTIVE_BOSS_BATTLES:
            skipped += 1
            continue

        if not is_boss_enabled(chat_id):
            skipped += 1
            continue

        try:
            if await _start_boss_battle(
                context,
                chat_id,
                include_registrations=True,
            ):
                _boss_clear_registrations(chat_id)
                started += 1
            else:
                skipped += 1

        except (Forbidden, BadRequest) as exc:
            set_boss_enabled(chat_id, False)
            disabled += 1
            logging.warning(
                "Отключаем ежедневного босса для чата %s: %s",
                chat_id,
                exc,
            )

        except Exception:
            logging.exception(
                "Ошибка запуска ежедневного босса в чате %s",
                chat_id,
            )

    logging.info(
        "Ежедневный босс: запущено=%s, пропущено=%s, "
        "отключено=%s, всего=%s",
        started,
        skipped,
        disabled,
        len(chats),
    )


async def _boss_join_timer(
    context,
    chat_id,
):
    try:
        await asyncio.sleep(BOSS_JOIN_TIMEOUT)
    except asyncio.CancelledError:
        return

    battle = ACTIVE_BOSS_BATTLES.get(chat_id)

    if not battle:
        return

    async with battle["lock"]:
        if battle["phase"] != "join":
            return

        if not battle["participants"]:
            ACTIVE_BOSS_BATTLES.pop(
                chat_id,
                None,
            )

            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=battle["message_id"],
                    text=(
                        f"💀 <b>{battle['boss']['name']}</b>\n\n"
                        f"Никто не осмелился вступить "
                        f"в битву.\n\n"
                        f"Босс ушёл ждать более "
                        f"храбрых гномов."
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass

            return

        battle["phase"] = "attack"

        await _boss_start_round(
            context,
            chat_id,
        )

