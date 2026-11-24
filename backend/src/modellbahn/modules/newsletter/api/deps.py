"""FastAPI dependencies of the newsletter API: services and who may do what."""

from typing import Annotated, Final

from fastapi import Depends, Request

from modellbahn.modules.identity.contracts.auth import (
    Customer,
    StaffMember,
    StaffRole,
    require_customer,
    require_staff,
)
from modellbahn.modules.newsletter.application.issues import IssueService
from modellbahn.modules.newsletter.application.subscriptions import SubscriptionService
from modellbahn.platform.http import app_state
from modellbahn.platform.ratelimit import rate_limit

NEWSLETTER_RATE_LIMITER: Final = "newsletter_rate_limiter"
"""Name on ``app.state`` of the limiter of the links from the mails."""


def get_subscription_service(request: Request) -> SubscriptionService:
    return app_state(request, "newsletter_subscription_service", SubscriptionService)


def get_issue_service(request: Request) -> IssueService:
    return app_state(request, "newsletter_issue_service", IssueService)


limit_newsletter = rate_limit(NEWSLETTER_RATE_LIMITER)

SubscriptionServiceDep = Annotated[SubscriptionService, Depends(get_subscription_service)]
IssueServiceDep = Annotated[IssueService, Depends(get_issue_service)]
CurrentReader = Annotated[Customer, Depends(require_customer)]
# The newsletter is the office's business, like the fairs.
NewsletterViewer = Annotated[StaffMember, Depends(require_staff(StaffRole.OWNER, StaffRole.STAFF))]
