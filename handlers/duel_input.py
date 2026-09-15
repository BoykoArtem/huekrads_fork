"""Pure input-normalization helpers for duel commands."""


def extract_username(update, context) -> str | None:
    """Return the first supplied duel opponent username, without ``@``."""
    if context.args:
        return context.args[0].strip().lstrip("@")

    if update.message and update.message.text:
        parts = update.message.text.split()
        if len(parts) > 1:
            return parts[1].strip().lstrip("@")

    return None
