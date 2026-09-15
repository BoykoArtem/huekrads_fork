from types import SimpleNamespace
import re


def callback_data(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_boss_keyboard_callback_data_contract():
    from handlers import duel

    attack = callback_data(duel._boss_attack_keyboard(3))
    block = callback_data(duel._boss_block_keyboard(3))
    assert attack == ["boss_attack_head_3", "boss_attack_body_3", "boss_attack_dick_3"]
    assert block == ["boss_block_head_3", "boss_block_body_3", "boss_block_dick_3"]
    for value in attack + block:
        assert re.fullmatch(r"boss_(attack|block)_(head|body|dick)_\d+", value)


def test_boss_registration_uses_isolated_database(tmp_path, monkeypatch, tg_user):
    from handlers import duel

    monkeypatch.setattr(duel, "_BOSS_REG_DB_PATH", tmp_path / "registrations.db")
    monkeypatch.setattr(duel, "_boss_today", lambda: "2025-01-01")
    assert duel._boss_register_user(-99, tg_user) is True
    assert duel._boss_register_user(-99, tg_user) is False
    assert duel._boss_get_registered_users(-99) == [(1001, "tester", "Tester", "User")]
    duel._boss_clear_registrations(-99)
    assert duel._boss_get_registered_users(-99) == []


def test_boss_state_helpers():
    from handlers import duel
    from handlers import duel_formatting
    from handlers import duel_text

    battle = {"participants": {1: {"alive": True}, 2: {"alive": False}}}
    assert duel._boss_alive_players is duel_text._boss_alive_players
    assert duel._boss_all_alive_chosen is duel_text._boss_all_alive_chosen
    assert duel._boss_phase_status is duel_text._boss_phase_status
    assert duel._boss_battle_hero is duel_text._boss_battle_hero
    assert duel._boss_player_title is duel_formatting.boss_player_title
    assert duel._boss_players_status_text is duel_formatting._boss_players_status_text
    assert duel._boss_phase_text is duel_formatting._boss_phase_text
    assert duel._boss_alive_players(battle) == [{"alive": True}]
    assert duel._boss_all_alive_chosen({"participants": {1: {"alive": True, "attack": "head"}}}, "attack")
    participant = {"alive": True, "attack": "head", "block": None}
    assert duel._boss_phase_status(participant, "attack") == duel._legacy_boss_phase_status(participant, "attack")
    players = [
        {"alive": False, "hits": 2, "blocks": 0, "rounds_survived": 1},
        {"alive": True, "hits": 2, "blocks": 0, "rounds_survived": 1},
    ]
    assert duel._boss_battle_hero(players) == duel._legacy_boss_battle_hero(players)
    assert duel._boss_player_title({"data": {"username": "@boss_tester"}}) == "boss_tester"
    phase_battle = {
        "boss": {"name": "Тестер"}, "round": 2, "hits": 1, "phase": "attack",
        "participants": {1: {"alive": True, "data": {"username": "@alive"}, "attack": "head"}, 2: {"alive": False, "data": {"display_name": "Dead"}}},
    }
    assert f"<b>1 / {duel.BOSS_REQUIRED_HITS}</b>" in duel._boss_phase_text(
        phase_battle, duel.BOSS_REQUIRED_HITS
    )
    assert "<b>alive</b> — 🟢 выбрал" in duel._boss_players_status_text(phase_battle)
    phase_battle["phase"] = "block"
    assert "<b>ФАЗА ЗАЩИТЫ</b>" in duel._boss_phase_text(
        phase_battle, duel.BOSS_REQUIRED_HITS
    )
