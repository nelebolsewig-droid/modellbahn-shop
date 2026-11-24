"""The newsletter in the Stellwerk: readers, the next issue, its preview, past issues."""

from fastapi import APIRouter

from modellbahn.modules.newsletter.api.deps import (
    IssueServiceDep,
    NewsletterViewer,
    SubscriptionServiceDep,
)
from modellbahn.modules.newsletter.api.errors import STAFF_ACCESS
from modellbahn.modules.newsletter.api.schemas import (
    NewsletterOverviewOut,
    NewsletterPreviewOut,
    PastIssueOut,
)
from modellbahn.platform.errors import problems

router = APIRouter(prefix="/admin", tags=["admin-newsletter"])


@router.get(
    "/newsletter",
    operation_id="getNewsletterOverview",
    summary="Readers, the next issue and the past ones",
    responses=problems(STAFF_ACCESS, unsafe=False, validated=False),
)
async def overview(
    _: NewsletterViewer, issues: IssueServiceDep, subscriptions: SubscriptionServiceDep
) -> NewsletterOverviewOut:
    counts = await subscriptions.counts()
    found = await issues.overview()
    return NewsletterOverviewOut(
        confirmed=counts.confirmed,
        pending=counts.pending,
        issue_days=list(found.issue_days),
        next_issue=found.next_issue,
        waiting=found.waiting,
        recent=[
            PastIssueOut(
                number=past.number,
                issue_date=past.issue_date,
                new_models=past.new_models,
                sent=past.sent,
            )
            for past in found.recent
        ],
    )


@router.get(
    "/newsletter/preview",
    operation_id="previewNewsletter",
    summary="The next issue as a sample reader would get it",
    responses=problems(STAFF_ACCESS, unsafe=False, validated=False),
)
async def preview(_: NewsletterViewer, issues: IssueServiceDep) -> NewsletterPreviewOut:
    mail, sample = await issues.preview()
    return NewsletterPreviewOut(subject=mail.subject, html=mail.html, sample_owns=sample)
