from handlers.duel_state import (
    _advance_duel_round,
    _is_miss_roll,
    _is_suicide_roll,
    _resolve_zone_outcome,
    _set_attack_choice,
)


def test_suicide_roll_boundary():
    assert _is_suicide_roll(0.009999) is True
    assert _is_suicide_roll(0.01) is False


def test_miss_roll_boundary():
    assert _is_miss_roll(0.049999) is True
    assert _is_miss_roll(0.05) is False


def test_zone_outcome_distinguishes_block_and_hit():
    assert _resolve_zone_outcome("head", "head") == "block"
    assert _resolve_zone_outcome("head", "body") == "hit"


def test_set_attack_choice_mutates_state_in_place():
    duel_state = {
        "phase": "attack",
        "attack_zone": None,
        "turn_id": 7,
        "unchanged": object(),
    }
    original_state = duel_state
    unchanged = duel_state["unchanged"]

    result = _set_attack_choice(duel_state, "body")

    assert result is None
    assert duel_state is original_state
    assert duel_state == {
        "phase": "block",
        "attack_zone": "body",
        "turn_id": 8,
        "unchanged": unchanged,
    }


def test_advance_duel_round_swaps_roles_and_mutates_state_in_place():
    attacker_tg = object()
    defender_tg = object()
    attacker_data = {"user_id": 1}
    defender_data = {"user_id": 2}
    duel_state = {
        "attacker_tg": attacker_tg,
        "defender_tg": defender_tg,
        "attacker_data": attacker_data,
        "defender_data": defender_data,
        "phase": "block",
        "attack_zone": "head",
        "round": 3,
        "turn_id": 12,
    }
    original_state = duel_state

    result = _advance_duel_round(duel_state)

    assert result is None
    assert duel_state is original_state
    assert duel_state["attacker_tg"] is defender_tg
    assert duel_state["defender_tg"] is attacker_tg
    assert duel_state["attacker_data"] is defender_data
    assert duel_state["defender_data"] is attacker_data
    assert duel_state["phase"] == "attack"
    assert duel_state["attack_zone"] is None
    assert duel_state["round"] == 4
    assert duel_state["turn_id"] == 13
