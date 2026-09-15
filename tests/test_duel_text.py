from handlers.duel_text import (
    TARGET_NAMES,
    _build_duel_block_text,
    _build_duel_miss_text,
)


def test_build_duel_miss_text_composes_current_html():
    assert _build_duel_miss_text(
        "Первый",
        "делает замах",
        "head",
        "промахивается мимо цели!",
        "Второй",
        "Первый",
        30,
    ) == (
        "💨 <b>ПРОМАХ!</b>\n"
        "<b>Первый</b> делает замах "
        f"в зону ({TARGET_NAMES['head']}), "
        "но промахивается мимо цели!\n\n"
        "🔄 <b>Смена ролей!</b>\n"
        "⚔️ Атакует: <b>Второй</b>\n"
        "🛡️ Защищается: <b>Первый</b>\n\n"
        "⏳ У <b>Второй</b> есть 30 секунд на удар:"
    )


def test_build_duel_block_text_composes_current_html():
    assert _build_duel_block_text(
        "Первый",
        "Второй",
        "делает замах",
        "body",
        "ставит надёжный блок!",
        "Второй",
        "Первый",
        30,
    ) == (
        "🛡️ <b>БЛОК СРАБОТАЛ!</b>\n"
        "<b>Первый</b> делает замах "
        f"в зону ({TARGET_NAMES['body']}), "
        "но <b>Второй</b> ставит надёжный блок!\n\n"
        "🔄 <b>Инициатива переходит!</b>\n"
        "⚔️ Атакует: <b>Второй</b>\n"
        "🛡️ Защищается: <b>Первый</b>\n\n"
        "⏳ У <b>Второй</b> есть 30 секунд на удар:"
    )
