"""Formatting adapters used by duel and boss output."""

from database import format_user_title
from handlers.duel_text import _boss_alive_players, _boss_phase_status


def boss_player_title(participant: dict) -> str:
    """Format the stored user data of a boss participant for display."""
    return format_user_title(participant["data"])


def _boss_players_status_text(battle):
    lines = []
    for participant in battle["participants"].values():
        title = boss_player_title(participant)
        status = _boss_phase_status(participant, battle["phase"])
        lines.append(f"• <b>{title}</b> — {status}")
    return "\n".join(lines)


def _boss_phase_text(battle, required_hits: int):
    boss = battle["boss"]
    alive_count = len(_boss_alive_players(battle))
    total_count = len(battle["participants"])

    if battle["phase"] == "attack":
        return (
            f"💀 <b>{boss['name']} — РАУНД {battle['round']}</b>\n\n"
            f"⚔️ <b>ФАЗА АТАКИ</b>\n"
            f"Каждый живой игрок выбирает, куда ударить босса.\n\n"
            f"🎯 Урон боссу: <b>{battle['hits']} / {required_hits}</b>\n"
            f"👥 В живых: <b>{alive_count} / {total_count}</b>\n\n"
            f"<b>Игроки:</b>\n{_boss_players_status_text(battle)}\n\n"
            f"⚔️ Выберите зону атаки:"
        )

    return (
        f"💀 <b>{boss['name']} — РАУНД {battle['round']}</b>\n\n"
        f"🛡 <b>ФАЗА ЗАЩИТЫ</b>\n"
        f"Босс сейчас атакует. Каждый живой игрок выбирает, какую зону защищать.\n\n"
        f"🎯 Урон боссу: <b>{battle['hits']} / {required_hits}</b>\n"
        f"👥 В живых: <b>{alive_count} / {total_count}</b>\n\n"
        f"<b>Игроки:</b>\n{_boss_players_status_text(battle)}\n\n"
        f"🛡 Выберите зону защиты:"
    )
