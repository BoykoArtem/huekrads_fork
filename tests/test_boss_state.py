import copy


def test_begin_boss_round_applies_normal_transition_to_all_participants():
    from handlers.boss_state import _begin_boss_round

    battle = {
        "round": 7,
        "phase": "resolving",
        "boss_attack": "body",
        "boss_block": "head",
        "participants": {
            1: {"attack": "head", "block": "dick", "alive": True},
            2: {"attack": "body", "block": "head", "alive": False},
        },
    }

    _begin_boss_round(battle, "dick", "body")

    assert battle["round"] == 8
    assert battle["phase"] == "attack"
    assert battle["boss_attack"] == "dick"
    assert battle["boss_block"] == "body"
    assert battle["participants"][1]["attack"] is None
    assert battle["participants"][1]["block"] is None
    assert battle["participants"][2]["attack"] is None
    assert battle["participants"][2]["block"] is None


def test_begin_boss_round_mutates_in_place_and_preserves_unrelated_state():
    from handlers.boss_state import _begin_boss_round

    first = {
        "attack": "head",
        "block": "body",
        "alive": True,
        "hits": 3,
        "custom": {"marker": 1},
    }
    second = {
        "attack": "dick",
        "block": "head",
        "alive": False,
        "death_round": 4,
    }
    participants = {10: first, 20: second}
    battle = {
        "round": 4,
        "phase": "custom-phase",
        "boss_attack": "head",
        "boss_block": "dick",
        "participants": participants,
        "hits": 9,
        "boss": {"name": "Неизменный Босс"},
        "message_id": 123,
    }
    unrelated_battle = {
        key: copy.deepcopy(value)
        for key, value in battle.items()
        if key not in {
            "round",
            "phase",
            "boss_attack",
            "boss_block",
            "participants",
        }
    }
    first_unrelated = {"alive": True, "hits": 3, "custom": {"marker": 1}}
    second_unrelated = {"alive": False, "death_round": 4}
    battle_identity = id(battle)
    participants_identity = id(participants)
    participant_identities = {user_id: id(value) for user_id, value in participants.items()}

    result = _begin_boss_round(battle, "body", "head")

    assert result is None
    assert id(battle) == battle_identity
    assert id(battle["participants"]) == participants_identity
    assert {
        user_id: id(value)
        for user_id, value in battle["participants"].items()
    } == participant_identities
    assert {
        key: value
        for key, value in battle.items()
        if key not in {
            "round",
            "phase",
            "boss_attack",
            "boss_block",
            "participants",
        }
    } == unrelated_battle
    assert {
        key: value
        for key, value in first.items()
        if key not in {"attack", "block"}
    } == first_unrelated
    assert {
        key: value
        for key, value in second.items()
        if key not in {"attack", "block"}
    } == second_unrelated
