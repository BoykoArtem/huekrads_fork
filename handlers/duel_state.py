"""Deterministic state transitions for an interactive duel."""


def _is_suicide_roll(suicide_roll: float) -> bool:
    return suicide_roll < 0.01


def _is_miss_roll(miss_roll: float) -> bool:
    return miss_roll < 0.05


def _resolve_zone_outcome(strike_zone: str, block_zone: str) -> str:
    return "block" if strike_zone == block_zone else "hit"


def _set_attack_choice(duel_state: dict, strike_zone: str) -> None:
    duel_state["attack_zone"] = strike_zone
    duel_state["phase"] = "block"
    duel_state["turn_id"] += 1


def _advance_duel_round(duel_state: dict) -> None:
    duel_state["attacker_tg"], duel_state["defender_tg"] = (
        duel_state["defender_tg"],
        duel_state["attacker_tg"],
    )
    duel_state["attacker_data"], duel_state["defender_data"] = (
        duel_state["defender_data"],
        duel_state["attacker_data"],
    )
    duel_state["phase"] = "attack"
    duel_state["attack_zone"] = None
    duel_state["round"] += 1
    duel_state["turn_id"] += 1
