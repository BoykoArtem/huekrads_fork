"""Pure state transitions for boss battles."""


def _begin_boss_round(battle, boss_attack, boss_block):
    battle["round"] += 1
    battle["phase"] = "attack"
    battle["boss_attack"] = boss_attack
    battle["boss_block"] = boss_block

    for participant in battle["participants"].values():
        participant["attack"] = None
        participant["block"] = None
