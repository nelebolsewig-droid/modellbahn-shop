"""FastAPI dependencies of the site API: services, the imprint and who may do what."""

from typing import Annotated, Final

from fastapi import Depends, Request

from modellbahn.modules.identity.contracts.auth import StaffMember, StaffRole, require_staff
from modellbahn.modules.site.application.fairs import FairService
from modellbahn.modules.site.application.subscriptions import SubscriptionService
from modellbahn.modules.site.application.visits import VisitService
from modellbahn.platform.config import Settings
from modellbahn.platform.http import app_state
from modellbahn.platform.imprint import Imprint
from modellbahn.platform.ratelimit import rate_limit

FAIR_NEWS_RATE_LIMITER: Final = "fair_news_rate_limiter"
"""Name on ``app.state`` of the limiter of the sign-up form."""


def get_fair_service(request: Request) -> FairService:
    return app_state(request, "fair_service", FairService)


def get_subscription_service(request: Request) -> SubscriptionService:
    return app_state(request, "subscription_service", SubscriptionService)


def get_visit_service(request: Request) -> VisitService:
    return app_state(request, "visit_service", VisitService)


def get_imprint(request: Request) -> Imprint:
    return app_state(request, "imprint", Imprint)


def get_public_base_url(request: Request) -> str:
    """Where the shop is reachable, for the links in calendar entries."""
    return app_state(request, "settings", Settings).public_base_url


# Sign-ups per client address: the form must not become a way to mail strangers.
limit_fair_news = rate_limit(FAIR_NEWS_RATE_LIMITER)


FairServiceDep = Annotated[FairService, Depends(get_fair_service)]
SubscriptionServiceDep = Annotated[SubscriptionService, Depends(get_subscription_service)]
VisitServiceDep = Annotated[VisitService, Depends(get_visit_service)]
ImprintDep = Annotated[Imprint, Depends(get_imprint)]
PublicBaseUrlDep = Annotated[str, Depends(get_public_base_url)]

# Fairs are the shop's public face: owner and staff keep them, packers have no business there.
FairEditor = Annotated[StaffMember, Depends(require_staff(StaffRole.OWNER, StaffRole.STAFF))]
# The visitor counts are the office's business, like the fairs.
VisitViewer = Annotated[StaffMember, Depends(require_staff(StaffRole.OWNER, StaffRole.STAFF))]
