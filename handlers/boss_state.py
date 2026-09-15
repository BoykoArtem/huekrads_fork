"""Pure state transitions for boss battles."""


def _begin_boss_round(battle, boss_attack, boss_block):
    battle["round"] += 1
    battle["phase"] = "attack"
    battle["boss_attack"] = boss_attack
    battle["boss_block"] = boss_block

    for participant in battle["participants"].values():
        participant["attack"] = None
        participant["block"] = None


def _apply_boss_round_result(battle, required_hits):
    boss_attack = battle["boss_attack"]
    boss_block = battle["boss_block"]
    round_results = []

    for participant in battle["participants"].values():
        if not participant["alive"]:
            continue

        attack = participant["attack"]
        block = participant["block"]
        hit = attack != boss_block

        if hit:
            battle["hits"] += 1
            participant["hits"] += 1
        else:
            participant["misses"] += 1

        survived = block == boss_attack

        if survived:
            participant["blocks"] += 1
            participant["rounds_survived"] += 1
        else:
            participant["alive"] = False
            participant["death_round"] = battle["round"]
            participant["death_by_zone"] = boss_attack
            participant["death_defended_zone"] = block
            participant["death_attack_zone"] = attack

        round_results.append({
            "participant": participant,
            "attack": attack,
            "block": block,
            "hit": hit,
            "survived": survived,
        })

    alive_after = sum(
        1
        for participant in battle["participants"].values()
        if participant["alive"]
    )
    victory = battle["hits"] >= required_hits
    defeat = alive_after == 0
    outcome = "victory" if victory else "defeat" if defeat else "continue"
    battle["phase"] = "resolving"

    return {
        "victory": victory,
        "defeat": defeat,
        "outcome": outcome,
        "alive_after": alive_after,
        "round_results": round_results,
    }
