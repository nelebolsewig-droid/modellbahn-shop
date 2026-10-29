"""The shop's rule for shipping addresses, for a marketplace to check an order with.

Plain Python like the domain it comes from: importing it keeps a layer free of SQL.
"""

from modellbahn.modules.sales.domain.errors import InvalidFieldError
from modellbahn.modules.sales.domain.model import PostalAddress

__all__ = ["address_problem"]


def address_problem(
    *, recipient: str, street: str, postal_code: str, city: str, country_code: str
) -> str | None:
    """Why the shop cannot ship to this address, in a few words; None if it can."""
    try:
        PostalAddress.create(
            recipient=recipient,
            street=street,
            postal_code=postal_code,
            city=city,
            country_code=country_code,
        )
    except InvalidFieldError as error:
        return f"address {error.field}: {error.code}"
    return None
