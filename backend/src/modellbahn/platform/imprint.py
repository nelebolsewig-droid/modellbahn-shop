"""Who runs the shop: the provider details of the imprint (§ 5 DDG), from the settings.

The same details close every e-mail, so a customer always knows who wrote to them.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Imprint:
    """Name, address and contact of the shop's operator. Empty strings: not configured."""

    shop_name: str
    company: str
    owner: str
    street: str
    postal_code: str
    city: str
    country: str
    phone: str
    email: str
    vat_id: str

    @property
    def is_complete(self) -> bool:
        """Everything § 5 DDG asks for is there (the VAT ID only where one exists)."""
        return all((self.company, self.owner, self.street, self.postal_code, self.city, self.email))

    def address_line(self) -> str:
        """``Glambecker Straße 2, 17235 Neustrelitz``; empty if not configured."""
        place = " ".join(part for part in (self.postal_code, self.city) if part)
        return ", ".join(part for part in (self.street, place) if part)

    def mail_footer(self) -> tuple[str, ...]:
        """The sender as it closes each e-mail: who, where, how to reach them."""
        who = " · ".join(part for part in (self.company, self.owner) if part)
        reach = " · ".join(part for part in (self.email, self.phone) if part)
        return tuple(line for line in (who, self.address_line(), reach) if line)
