"""Outgoing e-mail: message model, German layout, SMTP and in-memory mailers.

Modules describe *what* a mail says as :class:`MailContent`; :func:`compose`
renders it into the shop's common German layout as plain text plus simple HTML.
"""

import html
from collections.abc import Sequence
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from typing import Final, Protocol

import aiosmtplib

from modellbahn.platform.config import Settings

SMTP_TIMEOUT_SECONDS: Final = 30.0


@dataclass(frozen=True, slots=True)
class OutgoingMail:
    """A fully rendered e-mail, ready to send."""

    to: str
    subject: str
    text: str
    html: str


@dataclass(frozen=True, slots=True)
class MailAction:
    """The one call to action of a mail, rendered as a button and as a plain link."""

    label: str
    url: str


@dataclass(frozen=True, slots=True)
class MailContent:
    """What a mail says, independent of its layout. All texts are plain (unescaped)."""

    subject: str
    greeting: str
    paragraphs: Sequence[str]
    action: MailAction | None = None
    closing: Sequence[str] = field(default_factory=tuple)


class Mailer(Protocol):
    """Sends e-mails. Implementations raise on failure so the caller can retry."""

    async def send(self, mail: OutgoingMail) -> None:
        """Deliver ``mail``; raise if that is not possible."""
        ...


def compose(content: MailContent, *, to: str, shop_name: str) -> OutgoingMail:
    """Render ``content`` in the shop's German layout."""
    return OutgoingMail(
        to=to,
        subject=content.subject,
        text=_render_text(content, shop_name),
        html=_render_html(content, shop_name),
    )


_FOOTER: Final = "Diese E-Mail wurde automatisch versendet. Antworten darauf erreichen niemanden."


def _render_text(content: MailContent, shop_name: str) -> str:
    blocks = [content.greeting, *content.paragraphs]
    if content.action is not None:
        blocks.append(f"{content.action.label}:\n{content.action.url}")
    blocks.extend(content.closing)
    blocks.append(f"Viele Grüße\n{shop_name}")
    blocks.append(f"-- \n{_FOOTER}")
    return "\n\n".join(blocks) + "\n"


def _render_html(content: MailContent, shop_name: str) -> str:
    def paragraph(text: str) -> str:
        return f'<p style="margin:0 0 16px">{html.escape(text)}</p>'

    parts = [paragraph(content.greeting), *(paragraph(p) for p in content.paragraphs)]
    if content.action is not None:
        url = html.escape(content.action.url, quote=True)
        label = html.escape(content.action.label)
        parts.append(
            '<p style="margin:24px 0">'
            f'<a href="{url}" style="background:#1b211f;color:#ffffff;padding:12px 20px;'
            f'border-radius:4px;text-decoration:none;display:inline-block">{label}</a></p>'
            '<p style="margin:0 0 16px;font-size:13px;color:#555">'
            "Falls der Knopf nicht funktioniert, öffne diesen Link:<br>"
            f'<a href="{url}">{url}</a></p>'
        )
    parts.extend(paragraph(p) for p in content.closing)
    parts.append(f'<p style="margin:0 0 16px">Viele Grüße<br>{html.escape(shop_name)}</p>')
    body = "\n".join(parts)
    return (
        '<!doctype html>\n<html lang="de">\n<head><meta charset="utf-8">'
        f"<title>{html.escape(content.subject)}</title></head>\n"
        '<body style="margin:0;padding:24px;background:#e8e7de;color:#1b211f;'
        'font-family:Helvetica,Arial,sans-serif;font-size:15px;line-height:1.5">\n'
        '<div style="max-width:560px;margin:0 auto;background:#ffffff;padding:32px;'
        'border-radius:6px">\n'
        f"{body}\n"
        f'<hr style="border:none;border-top:1px solid #d5d4ca;margin:24px 0">'
        f'<p style="margin:0;font-size:12px;color:#666">{html.escape(_FOOTER)}</p>\n'
        "</div>\n</body>\n</html>\n"
    )


class SmtpMailer:
    """Sends mails through an SMTP server (Mailpit in development)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sender_domain = parseaddr(settings.smtp_from)[1].rpartition("@")[2]

    async def send(self, mail: OutgoingMail) -> None:
        settings = self._settings
        message = EmailMessage()
        message["From"] = settings.smtp_from
        message["To"] = mail.to
        message["Subject"] = mail.subject
        message["Date"] = formatdate(usegmt=True)
        message["Message-ID"] = make_msgid(domain=self._sender_domain)
        message.set_content(mail.text)
        message.add_alternative(mail.html, subtype="html")
        password = settings.smtp_password.get_secret_value() if settings.smtp_password else None
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            start_tls=settings.smtp_starttls,
            username=settings.smtp_username,
            password=password,
            timeout=SMTP_TIMEOUT_SECONDS,
        )


class InMemoryMailer:
    """Collects mails instead of sending them; meant for tests."""

    def __init__(self) -> None:
        self.sent: list[OutgoingMail] = []

    async def send(self, mail: OutgoingMail) -> None:
        self.sent.append(mail)
