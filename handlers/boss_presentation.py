"""Pure text composition for boss battle results."""

import random

from handlers.duel_formatting import boss_player_title as _boss_player_title
from handlers.duel_text import _boss_battle_hero, _plural_rounds


BOSS_REQUIRED_HITS = 5

BOSS_ZONE_NAMES = {
    "head": "Голова",
    "body": "Торс",
    "dick": "Хуй",
}


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
