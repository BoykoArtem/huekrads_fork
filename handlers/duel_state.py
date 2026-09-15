"""Deterministic state transitions for an interactive duel."""


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
