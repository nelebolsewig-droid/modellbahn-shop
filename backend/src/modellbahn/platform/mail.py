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
class MailRow:
    """One row of a table in a mail, e.g. an order line: a description and an amount.

    ``strong`` rows (a total) are set in bold in HTML and set off by a rule in plain text.
    """

    label: str
    value: str
    strong: bool = False


@dataclass(frozen=True, slots=True)
class MailContent:
    """What a mail says, independent of its layout. All texts are plain (unescaped).

    ``rows`` form a table between the paragraphs and the call to action.
    """

    subject: str
    greeting: str
    paragraphs: Sequence[str]
    action: MailAction | None = None
    closing: Sequence[str] = field(default_factory=tuple)
    rows: Sequence[MailRow] = field(default_factory=tuple)


class Mailer(Protocol):
    """Sends e-mails. Implementations raise on failure so the caller can retry."""

    async def send(self, mail: OutgoingMail) -> None:
        """Deliver ``mail``; raise if that is not possible."""
        ...


def compose(
    content: MailContent, *, to: str, shop_name: str, sender: Sequence[str] = ()
) -> OutgoingMail:
    """Render ``content`` in the shop's German layout.

    ``sender`` are the lines that say who sent the mail (name, address, contact), set
    small at the very end, as the footer of a business letter.
    """
    return OutgoingMail(
        to=to,
        subject=content.subject,
        text=_render_text(content, shop_name, sender),
        html=_render_html(content, shop_name, sender),
    )


_LABEL_WIDTH: Final = 40
_FOOTER: Final = "Diese E-Mail wurde automatisch versendet. Antworten darauf erreichen niemanden."


def _render_text(content: MailContent, shop_name: str, sender: Sequence[str]) -> str:
    blocks = [content.greeting, *content.paragraphs]
    if content.rows:
        blocks.append(_text_table(content.rows))
    if content.action is not None:
        blocks.append(f"{content.action.label}:\n{content.action.url}")
    blocks.extend(content.closing)
    blocks.append(f"Viele Grüße\n{shop_name}")
    blocks.append("\n".join(["-- ", *sender, _FOOTER]))
    return "\n\n".join(blocks) + "\n"


def _text_table(rows: Sequence[MailRow]) -> str:
    # Plain text has no columns: labels are padded, amounts aligned on the right, and a
    # label too long for its column gets a line of its own above the amount.
    width = max(len(row.value) for row in rows)
    lines: list[str] = []
    for row in rows:
        if row.strong:
            lines.append("-" * (_LABEL_WIDTH + 1 + width))
        if len(row.label) > _LABEL_WIDTH:
            lines.extend([row.label, f"{'':{_LABEL_WIDTH}} {row.value:>{width}}"])
        else:
            lines.append(f"{row.label:<{_LABEL_WIDTH}} {row.value:>{width}}")
    return "\n".join(lines)


def _html_table(rows: Sequence[MailRow]) -> str:
    cells = []
    for row in rows:
        weight = "font-weight:bold;border-top:1px solid #d5d4ca;" if row.strong else ""
        cells.append(
            f'<tr><td style="padding:6px 12px 6px 0;{weight}">{html.escape(row.label)}</td>'
            f'<td style="padding:6px 0;text-align:right;white-space:nowrap;{weight}">'
            f"{html.escape(row.value)}</td></tr>"
        )
    return (
        '<table role="presentation" style="width:100%;border-collapse:collapse;'
        'margin:0 0 16px;font-size:14px">' + "".join(cells) + "</table>"
    )


def _render_html(content: MailContent, shop_name: str, sender: Sequence[str]) -> str:
    def paragraph(text: str) -> str:
        return f'<p style="margin:0 0 16px">{html.escape(text)}</p>'

    parts = [paragraph(content.greeting), *(paragraph(p) for p in content.paragraphs)]
    if content.rows:
        parts.append(_html_table(content.rows))
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
        f"{_html_sender(sender)}"
        f'<p style="margin:0;font-size:12px;color:#666">{html.escape(_FOOTER)}</p>\n'
        "</div>\n</body>\n</html>\n"
    )


def _html_sender(sender: Sequence[str]) -> str:
    if not sender:
        return ""
    lines = "<br>".join(html.escape(line) for line in sender)
    return f'<p style="margin:0 0 8px;font-size:12px;color:#666">{lines}</p>'


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
