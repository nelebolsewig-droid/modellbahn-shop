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
class MailAttachment:
    """A file sent along, e.g. an invoice as PDF."""

    filename: str
    content: bytes
    content_type: str = "application/pdf"


@dataclass(frozen=True, slots=True)
class OutgoingMail:
    """A fully rendered e-mail, ready to send."""

    to: str
    subject: str
    text: str
    html: str
    attachments: Sequence[MailAttachment] = ()


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
    content: MailContent,
    *,
    to: str,
    shop_name: str,
    sender: Sequence[str] = (),
    attachments: Sequence[MailAttachment] = (),
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
        attachments=tuple(attachments),
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
        weight = f"font-weight:bold;border-top:1px solid {_RULE};" if row.strong else ""
        cells.append(
            f'<tr><td style="padding:6px 12px 6px 0;{weight}">{html.escape(row.label)}</td>'
            f'<td style="padding:6px 0;text-align:right;white-space:nowrap;{weight}">'
            f"{html.escape(row.value)}</td></tr>"
        )
    return (
        '<table role="presentation" style="width:100%;border-collapse:collapse;'
        'margin:0 0 16px;font-size:14px">' + "".join(cells) + "</table>"
    )


# The shop's colours (ADR 0030): espresso ink on a light page, mandarin for the button,
# the logo's red for the "adp" of the wordmark.
_INK: Final = "#26211e"
_INK_SECONDARY: Final = "#665b53"
_CANVAS: Final = "#faf6f0"
_RULE: Final = "#ddd0be"
_ACTION: Final = "#e8632b"
_LOGO_RED: Final = "#cc0000"


def _html_wordmark(shop_name: str) -> str:
    """The wordmark as text, so it shows even where a mail program holds back images:
    the part before the hyphen red, Times bold italic, the rest Arial bold (ADR 0030)."""
    cut = shop_name.find("-")
    head, rest = (shop_name[:cut].lower(), shop_name[cut:]) if cut > 0 else ("", shop_name)
    head_html = (
        f"<span style=\"font-family:'Times New Roman',Times,serif;font-style:italic;"
        f'font-weight:bold;font-size:30px;color:{_LOGO_RED}">{html.escape(head)}</span>'
        if head
        else ""
    )
    return (
        '<p style="margin:0 0 24px;line-height:1">'
        f"{head_html}"
        f'<span style="font-family:Arial,Helvetica,sans-serif;font-weight:bold;font-size:27px;'
        f'color:{_INK}">{html.escape(rest)}</span></p>'
        f'<div style="height:3px;width:56px;background:{_ACTION};margin:0 0 28px"></div>'
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
            f'<a href="{url}" style="background:{_ACTION};color:#ffffff;padding:12px 20px;'
            'font-weight:bold;text-decoration:none;display:inline-block">'
            f"{label}</a></p>"
            f'<p style="margin:0 0 16px;font-size:13px;color:{_INK_SECONDARY}">'
            "Falls der Knopf nicht funktioniert, öffne diesen Link:<br>"
            f'<a href="{url}" style="color:{_INK}">{url}</a></p>'
        )
    parts.extend(paragraph(p) for p in content.closing)
    parts.append(f'<p style="margin:0 0 16px">Viele Grüße<br>{html.escape(shop_name)}</p>')
    body = "\n".join(parts)
    return (
        '<!doctype html>\n<html lang="de">\n<head><meta charset="utf-8">'
        f"<title>{html.escape(content.subject)}</title></head>\n"
        f'<body style="margin:0;padding:24px;background:{_CANVAS};color:{_INK};'
        'font-family:Helvetica,Arial,sans-serif;font-size:15px;line-height:1.5">\n'
        '<div style="max-width:560px;margin:0 auto;background:#ffffff;padding:32px;'
        f'border-top:4px solid {_INK}">\n'
        f"{_html_wordmark(shop_name)}\n"
        f"{body}\n"
        f'<hr style="border:none;border-top:1px solid {_RULE};margin:24px 0">'
        f"{_html_sender(sender)}"
        f'<p style="margin:0;font-size:12px;color:{_INK_SECONDARY}">{html.escape(_FOOTER)}</p>\n'
        "</div>\n</body>\n</html>\n"
    )


def _html_sender(sender: Sequence[str]) -> str:
    if not sender:
        return ""
    lines = "<br>".join(html.escape(line) for line in sender)
    return f'<p style="margin:0 0 8px;font-size:12px;color:{_INK_SECONDARY}">{lines}</p>'


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
        for attachment in mail.attachments:
            maintype, _, subtype = attachment.content_type.partition("/")
            message.add_attachment(
                attachment.content,
                maintype=maintype,
                subtype=subtype,
                filename=attachment.filename,
            )
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
