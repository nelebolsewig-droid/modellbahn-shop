"""Amounts of money as people read them in the shop."""


def format_euro(cents: int) -> str:
    """German notation, e.g. ``1.234,50 €`` (with a no-break space before the sign)."""
    euros, rest = divmod(cents, 100)
    return f"{euros:,}".replace(",", ".") + f",{rest:02d}\u00a0€"
