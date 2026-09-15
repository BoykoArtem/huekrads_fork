"""Formatting adapters used by duel and boss output."""

from database import format_user_title


def boss_player_title(participant: dict) -> str:
    """Format the stored user data of a boss participant for display."""
    return format_user_title(participant["data"])
