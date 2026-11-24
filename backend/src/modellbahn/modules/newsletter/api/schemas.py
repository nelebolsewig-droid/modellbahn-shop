"""Request and response bodies of the newsletter API."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NewsletterChoiceIn(_Request):
    subscribed: bool = Field(
        description="True asks for the newsletter (confirmation by mail), false leaves it."
    )


class NewsletterStatusOut(BaseModel):
    status: Literal["none", "pending", "confirmed"] = Field(
        description="``pending``: the confirmation link was mailed (or follows the "
        "verification of the address) and not followed yet."
    )


class NewsletterTokenIn(_Request):
    token: str = Field(min_length=1, max_length=200)


class PastIssueOut(BaseModel):
    number: int
    issue_date: date
    new_models: int
    sent: int = Field(description="Readers the issue went to.")


class NewsletterOverviewOut(BaseModel):
    confirmed: int = Field(description="Readers who confirmed.")
    pending: int = Field(description="Asked, not confirmed yet; deleted after two weeks.")
    issue_days: list[int] = Field(description="Days of the month an issue goes out.")
    next_issue: date | None = Field(
        description="The next issue day; it goes out only if there are new models."
    )
    waiting: list[str] = Field(description="Models new since the last issue.")
    recent: list[PastIssueOut]


class NewsletterPreviewOut(BaseModel):
    subject: str
    html: str
    sample_owns: str | None = Field(
        description="The model the sample reader is assumed to own, for the suggestions."
    )
