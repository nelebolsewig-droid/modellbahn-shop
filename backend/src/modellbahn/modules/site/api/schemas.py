"""Request and response bodies of the site API."""

from datetime import date, datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from modellbahn.modules.site.domain.dates import date_range
from modellbahn.modules.site.domain.model import (
    BOOTH_MAX_LENGTH,
    CITY_MAX_LENGTH,
    EMAIL_MAX_LENGTH,
    FAIR_NAME_MAX_LENGTH,
    HOURS_MAX_LENGTH,
    NOTE_MAX_LENGTH,
    POSTAL_CODE_MAX_LENGTH,
    STREET_MAX_LENGTH,
    URL_MAX_LENGTH,
    VENUE_MAX_LENGTH,
    Fair,
    FairDetails,
)
from modellbahn.platform.imprint import Imprint


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Fairs ----------------------------------------------------------------------------


class FairOut(BaseModel):
    """A fair as the shop shows it."""

    id: UUID
    name: str = Field(examples=["Kleinserienmesse Dresden"])
    venue: str = Field(examples=["JohannStadthalle"])
    street: str = Field(examples=["Holbeinstraße 68"])
    postal_code: str = Field(examples=["01307"])
    city: str = Field(examples=["Dresden"])
    booth: str = Field(examples=["Halle 3, Stand L04"])
    hours: str = Field(description="Opening hours, one line per day.")
    website_url: str
    note: str
    starts_on: date
    ends_on: date
    when: str = Field(description="The dates in German.", examples=["7. November 2026"])

    @classmethod
    def from_fair(cls, fair: Fair) -> Self:
        return cls(
            id=fair.id,
            name=fair.name,
            venue=fair.venue,
            street=fair.street,
            postal_code=fair.postal_code,
            city=fair.city,
            booth=fair.booth,
            hours=fair.hours,
            website_url=fair.website_url,
            note=fair.note,
            starts_on=fair.starts_on,
            ends_on=fair.ends_on,
            when=date_range(fair.starts_on, fair.ends_on),
        )


class FairCalendarOut(BaseModel):
    upcoming: list[FairOut] = Field(description="Still to come or under way, the earliest first.")
    past: list[FairOut] = Field(description="The last few, the latest first.")


class AdminFairOut(FairOut):
    published: bool
    announced_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_fair(cls, fair: Fair) -> Self:
        return cls(
            **FairOut.from_fair(fair).model_dump(),
            published=fair.published,
            announced_at=fair.announced_at,
            created_at=fair.created_at,
            updated_at=fair.updated_at,
        )


class AdminFairListOut(BaseModel):
    items: list[AdminFairOut]


class FairIn(_Request):
    """Everything about a fair; editing sends all of it again."""

    name: str = Field(min_length=1, max_length=FAIR_NAME_MAX_LENGTH)
    venue: str = Field(default="", max_length=VENUE_MAX_LENGTH)
    street: str = Field(default="", max_length=STREET_MAX_LENGTH)
    postal_code: str = Field(default="", max_length=POSTAL_CODE_MAX_LENGTH)
    city: str = Field(min_length=1, max_length=CITY_MAX_LENGTH)
    booth: str = Field(default="", max_length=BOOTH_MAX_LENGTH)
    hours: str = Field(default="", max_length=HOURS_MAX_LENGTH)
    website_url: str = Field(default="", max_length=URL_MAX_LENGTH)
    note: str = Field(default="", max_length=NOTE_MAX_LENGTH)
    starts_on: date
    ends_on: date
    published: bool = False

    def details(self) -> FairDetails:
        return FairDetails(
            name=self.name,
            venue=self.venue,
            street=self.street,
            postal_code=self.postal_code,
            city=self.city,
            booth=self.booth,
            hours=self.hours,
            website_url=self.website_url,
            note=self.note,
            starts_on=self.starts_on,
            ends_on=self.ends_on,
        )


class AnnouncementOut(BaseModel):
    fair: AdminFairOut
    recipients: int = Field(description="Confirmed subscribers the worker is mailing now.")


# --- Fair news ------------------------------------------------------------------------


class SubscriptionIn(_Request):
    email: str = Field(min_length=3, max_length=EMAIL_MAX_LENGTH)
    consent: bool = Field(description="The visitor ticked the consent; must be true.")


class TokenIn(_Request):
    token: str = Field(min_length=1, max_length=200)


class SubscriptionCountsOut(BaseModel):
    confirmed: int
    pending: int = Field(description="Asked, not confirmed yet; deleted after a week.")


# --- Imprint --------------------------------------------------------------------------


class ImprintOut(BaseModel):
    """The provider details (§ 5 DDG); empty strings where nothing is configured yet."""

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
    complete: bool = Field(description="Everything § 5 DDG asks for is there.")

    @classmethod
    def from_imprint(cls, imprint: Imprint) -> Self:
        return cls(
            shop_name=imprint.shop_name,
            company=imprint.company,
            owner=imprint.owner,
            street=imprint.street,
            postal_code=imprint.postal_code,
            city=imprint.city,
            country=imprint.country,
            phone=imprint.phone,
            email=imprint.email,
            vat_id=imprint.vat_id,
            complete=imprint.is_complete,
        )
