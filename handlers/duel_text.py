"""Pure presentation helpers shared by duel and boss battle output.

This module deliberately has no Telegram, SQLite, or runtime-state imports.
"""

HUYANIE_TITLES = {
    10: "\U0001f346 \u041d\u0430\u0447\u0438\u043d\u0430\u044e\u0449\u0438\u0439 \u0425\u0443\u044f\u043d\u0438\u0441\u0442",
    20: "\U0001f346 \u041f\u043e\u0434\u043c\u0430\u0441\u0442\u0435\u0440\u044c\u0435 \u0425\u0443\u044f\u043d\u0438\u044f",
    30: "\U0001f346 \u041f\u0440\u0430\u043a\u0442\u0438\u043a\u0443\u044e\u0449\u0438\u0439 \u0425\u0443\u044f\u043d\u0438\u0441\u0442",
    40: "\U0001f346 \u041e\u043f\u044b\u0442\u043d\u044b\u0439 \u0425\u0443\u044f\u043d\u0438\u0441\u0442",
    50: "\U0001f346 \u041c\u0430\u0441\u0442\u0435\u0440 \u0425\u0443\u044f\u043d\u0438\u044f",
    60: "\U0001f346 \u0412\u0435\u043b\u0438\u043a\u0438\u0439 \u0425\u0443\u044f\u043d\u0438\u0441\u0442",
    70: "\U0001f346 \u0410\u0440\u0445\u0438\u043c\u0430\u0441\u0442\u0435\u0440 \u0425\u0443\u044f\u043d\u0438\u044f",
    80: "\U0001f346 \u0412\u0435\u0440\u0445\u043e\u0432\u043d\u044b\u0439 \u0425\u0443\u044f\u043d\u0438\u0441\u0442",
    90: "\U0001f346 \u0413\u0440\u043e\u0441\u0441\u043c\u0435\u0439\u0441\u0442\u0435\u0440 \u0425\u0443\u044f\u043d\u0438\u044f",
    100: "\U0001f451 \u0412\u0435\u043b\u0438\u043a\u0438\u0439 \u041c\u0430\u0433\u0438\u0441\u0442\u0440 \u0425\u0443\u044f\u043d\u0438\u044f",
}


def get_huyanie_title(stolen_dicks_count: int) -> str:
    count = int(stolen_dicks_count or 0)
    if count < 10:
        return "\u041d\u0435\u0442 \u0437\u0432\u0430\u043d\u0438\u044f"
    level = min((count // 10) * 10, 100)
    return HUYANIE_TITLES[level]


def _plural_rounds(value):
    value = int(value)
    if value % 10 == 1 and value % 100 != 11:
        return "\u0440\u0430\u0443\u043d\u0434"
    if 2 <= value % 10 <= 4 and not 12 <= value % 100 <= 14:
        return "\u0440\u0430\u0443\u043d\u0434\u0430"
    return "\u0440\u0430\u0443\u043d\u0434\u043e\u0432"


def _boss_alive_players(battle):
    return [participant for participant in battle["participants"].values() if participant["alive"]]


def _boss_all_alive_chosen(battle, field):
    alive = _boss_alive_players(battle)
    if not alive:
        return False
    return all(participant.get(field) is not None for participant in alive)


def _boss_phase_status(participant, phase):
    if not participant["alive"]:
        return "\U0001f480 \u043f\u043e\u0433\u0438\u0431"
    if phase == "attack":
        return "\U0001f7e2 \u0432\u044b\u0431\u0440\u0430\u043b" if participant.get("attack") is not None else "\U0001f7e1 \u0432\u044b\u0431\u0438\u0440\u0430\u0435\u0442"
    if phase == "block":
        return "\U0001f7e2 \u0432\u044b\u0431\u0440\u0430\u043b" if participant.get("block") is not None else "\U0001f7e1 \u0432\u044b\u0431\u0438\u0440\u0430\u0435\u0442"
    return ""


def _boss_battle_hero(participants):
    alive = [participant for participant in participants if participant["alive"]]
    if not participants:
        return None
    return max(
        participants,
        key=lambda participant: (
            participant.get("hits", 0),
            participant.get("blocks", 0),
            participant.get("rounds_survived", 0),
            1 if participant in alive else 0,
        ),
    )
