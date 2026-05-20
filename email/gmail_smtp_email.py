import os
import smtplib
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # Optional dependency
    load_dotenv = None


def _load_env() -> None:
    if load_dotenv is None:
        return
    env_path = Path(__file__).with_name(".env")
    load_dotenv(dotenv_path=env_path)


def _guess_image_subtype(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    if ext in {"jpg", "jpeg", "png", "gif", "webp"}:
        return "jpeg" if ext == "jpg" else ext
    return "png"


def _load_inline_image(path: Path, cid: str) -> tuple[str, bytes, str] | None:
    if not path.exists():
        return None
    return (cid, path.read_bytes(), _guess_image_subtype(path))


def _load_logo_inline() -> tuple[str, bytes, str] | None:
    logo_path = Path(__file__).with_name("pyrolert_light.png")
    return _load_inline_image(logo_path, "pyrolert-logo")


def _build_headcount_image(
    image_path: str | None,
    image_url: str | None,
    max_width_px: int = 520,
) -> tuple[str, list[tuple[str, bytes, str]] | None]:
    if image_url:
        html = (
            f'<img src="{image_url}" alt="Headcount capture" '
            f'style="display:block; max-width:{max_width_px}px; width:100%; height:auto; margin:8px 0 0;">'
        )
        return html, None

    if image_path:
        inline = _load_inline_image(Path(image_path), "headcount-image")
        if inline:
            html = (
                f'<img src="cid:headcount-image" alt="Headcount capture" '
                f'style="display:block; max-width:{max_width_px}px; width:100%; height:auto; margin:8px 0 0;">'
            )
            return html, [inline]

    return "", None


class GmailMailer:
    """Reusable Gmail SMTP client for lower latency sends."""

    def __init__(self, smtp_user: str, smtp_password: str) -> None:
        if not smtp_user or not smtp_password:
            raise RuntimeError("Missing smtp_user or smtp_password.")
        self._smtp_user = smtp_user
        self._smtp_password = smtp_password
        self._server: smtplib.SMTP | None = None

    def connect(self) -> None:
        if self._server is not None:
            return
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        server.starttls()
        server.login(self._smtp_user, self._smtp_password)
        self._server = server

    def close(self) -> None:
        if self._server is None:
            return
        try:
            self._server.quit()
        finally:
            self._server = None

    def send_hello(self, to_email: str) -> None:
        if self._server is None:
            raise RuntimeError("Call connect() before sending.")

        self.send_message(to_email, "Alert", "HIGH WARNING!")

    def send_message(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        inline_images: list[tuple[str, bytes, str]] | None = None,
    ) -> None:
        if self._server is None:
            raise RuntimeError("Call connect() before sending.")

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._smtp_user
        msg["To"] = to_email
        msg.set_content(body)
        if html_body:
            msg.add_alternative(html_body, subtype="html")
            if inline_images:
                html_part = msg.get_body(preferencelist=("html",))
                if html_part:
                    for cid, data, subtype in inline_images:
                        html_part.add_related(
                            data,
                            maintype="image",
                            subtype=subtype,
                            cid=cid,
                        )

        self._server.send_message(msg)

    def __enter__(self) -> "GmailMailer":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def send_hello(to_email: str, smtp_user: str, smtp_password: str) -> None:
    """One-off send using a new SMTP connection."""
    with GmailMailer(smtp_user, smtp_password) as mailer:
        mailer.send_hello(to_email)


def send_message(
    to_email: str,
    subject: str,
    body: str,
    smtp_user: str,
    smtp_password: str,
    html_body: str | None = None,
    inline_images: list[tuple[str, bytes, str]] | None = None,
) -> None:
    """One-off send using a new SMTP connection."""
    with GmailMailer(smtp_user, smtp_password) as mailer:
        mailer.send_message(to_email, subject, body, html_body, inline_images)


def send_hello_from_env(to_email: str) -> None:
    """Send an alert email via Gmail SMTP using env vars.

    Required environment variables:
    - GMAIL_SMTP_USER
    - GMAIL_SMTP_PASSWORD (app password recommended)
    """
    _load_env()
    smtp_user = os.getenv("GMAIL_SMTP_USER")
    smtp_password = os.getenv("GMAIL_SMTP_PASSWORD")

    if not smtp_user or not smtp_password:
        raise RuntimeError(
            "Missing GMAIL_SMTP_USER or GMAIL_SMTP_PASSWORD environment variables."
        )

    send_hello(to_email, smtp_user, smtp_password)


def send_message_from_env(
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    inline_images: list[tuple[str, bytes, str]] | None = None,
) -> None:
    """Send a custom email via Gmail SMTP using env vars."""
    _load_env()
    smtp_user = os.getenv("GMAIL_SMTP_USER")
    smtp_password = os.getenv("GMAIL_SMTP_PASSWORD")

    if not smtp_user or not smtp_password:
        raise RuntimeError(
            "Missing GMAIL_SMTP_USER or GMAIL_SMTP_PASSWORD environment variables."
        )

    send_message(to_email, subject, body, smtp_user, smtp_password, html_body, inline_images)


def send_bulk(
    recipients: list[str],
    subject: str,
    body: str,
    smtp_user: str,
    smtp_password: str,
    html_body: str | None = None,
    delay_seconds: float = 1.0,
) -> None:
    """Send the same email to multiple recipients using one connection."""
    if not recipients:
        raise RuntimeError("Recipients list is empty.")

    with GmailMailer(smtp_user, smtp_password) as mailer:
        for index, to_email in enumerate(recipients):
            mailer.send_message(to_email, subject, body, html_body)
            if delay_seconds > 0 and index < len(recipients) - 1:
                time.sleep(delay_seconds)


def send_bulk_from_env(
    recipients: list[str],
    subject: str,
    body: str,
    html_body: str | None = None,
    delay_seconds: float = 1.0,
) -> None:
    """Bulk send using env vars."""
    _load_env()
    smtp_user = os.getenv("GMAIL_SMTP_USER")
    smtp_password = os.getenv("GMAIL_SMTP_PASSWORD")

    if not smtp_user or not smtp_password:
        raise RuntimeError(
            "Missing GMAIL_SMTP_USER or GMAIL_SMTP_PASSWORD environment variables."
        )

    send_bulk(
        recipients,
        subject,
        body,
        smtp_user,
        smtp_password,
        html_body,
        delay_seconds,
    )


def send_alert_email(
    to_email: str,
    status: str,
    triggered_at: str | datetime | None,
    headcount: int | str,
    headcount_image_path: str | None = None,
    headcount_image_url: str | None = None,
) -> bool:
    """Send a formal alert email for Normal -> Warning/High Alert."""

    if triggered_at is None:
        triggered_at = datetime.now()
    if isinstance(triggered_at, datetime):
        triggered_at = triggered_at.strftime("%Y-%m-%d %H:%M:%S")
    subject = f"Alert Status: {status}"
    body = ""
    logo_inline = _load_logo_inline()
    logo_html = (
        '<img src="cid:pyrolert-logo" alt="Pyrolert Fire Alert Systems" '
        'style="display:block; max-width:220px; width:100%; height:auto; margin:0 auto;">'
        if logo_inline
        else '<h1 style="margin:0; font-size:22px; color:#ffffff; font-weight:700;">Pyrolert</h1>'
    )
    headcount_image_html, headcount_inline = _build_headcount_image(
        headcount_image_path,
        headcount_image_url,
    )
    headcount_block = (
        '<p style="font-size:14px; margin:0 0 8px; font-weight:700;">Recent Image Captured</p>'
        f'<div style="margin:0 0 16px;">{headcount_image_html}</div>'
        if headcount_image_html
        else ""
    )
    html_body = f"""
<!DOCTYPE html>
<html lang="en" style="margin:0; padding:0; background-color:#ffffff; font-family: Arial, sans-serif;">
    <head>
        <meta charset="UTF-8" />
        <title>Pyrolert Alert Notification</title>
    </head>
    <body style="margin:0; padding:0; background-color:#ffffff; font-family: Arial, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#ffffff; padding:32px 0;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff; border-radius:12px; border:1px solid #ececec; overflow:hidden;">
                        <tr>
                            <td align="center" style="background-color:#b00020; padding:20px 28px;">
                                {logo_html}
                            </td>
                        </tr>
                        <tr>
                            <td style="padding:28px; color:#333333;">
                                <h2 style="font-size:20px; font-weight:600; margin:0 0 12px 0; color:#b00020;">Alert Notification</h2>
                                <p style="font-size:15px; margin:0 0 16px 0; line-height:1.6;">
                                    This is an automated notification. The system status has turned to <strong>{status}</strong>. Kindly check the area.
                                </p>
                                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-size:15px; line-height:1.6; margin-bottom:16px;">
                                    <tr><td style="padding:6px 0 0; font-weight:700;">Alert Status:</td></tr>
                                    <tr><td style="padding:0 0 6px;">{status}</td></tr>
                                    <tr><td style="padding:6px 0 0; font-weight:700;">Triggered at:</td></tr>
                                    <tr><td style="padding:0 0 6px;">{triggered_at}</td></tr>
                                    <tr><td style="padding:6px 0 0; font-weight:700;">Current Headcount Detected:</td></tr>
                                    <tr><td style="padding:0 0 6px;">{headcount}</td></tr>
                                </table>
                                {headcount_block}
                                <p style="font-size:14px; margin:8px 0 0;">Sincerely,<br>Pyrolert Team</p>
                            </td>
                        </tr>
                        <tr>
                            <td style="background-color:#f7f7f7; padding:16px; text-align:center; font-size:12px; color:#888888;">
                                Pyrolert © 2026
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
</html>
"""
    inline_images: list[tuple[str, bytes, str]] = []
    if logo_inline:
        inline_images.append(logo_inline)
    if headcount_inline:
        inline_images.extend(headcount_inline)
    inline_payload = inline_images or None
    try:
        send_message_from_env(to_email, subject, body, html_body, inline_payload)
        return True
    except Exception:
        return False


def send_escalation_email(
    to_email: str,
    status: str,
    triggered_at: str | datetime | None,
    escalation_ts: str | datetime | None,
    headcount: int | str,
    headcount_image_path: str | None = None,
    headcount_image_url: str | None = None,
) -> bool:
    """Send a formal escalation email for Warning -> High Alert."""

    if triggered_at is None:
        triggered_at = datetime.now()
    if escalation_ts is None:
        escalation_ts = datetime.now()
    if isinstance(triggered_at, datetime):
        triggered_at = triggered_at.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(escalation_ts, datetime):
        escalation_ts = escalation_ts.strftime("%Y-%m-%d %H:%M:%S")
    subject = f"Escalation Notification: {status}"
    body = ""
    logo_inline = _load_logo_inline()
    logo_html = (
        '<img src="cid:pyrolert-logo" alt="Pyrolert Fire Alert Systems" '
        'style="display:block; max-width:220px; width:100%; height:auto; margin:0 auto;">'
        if logo_inline
        else '<h1 style="margin:0; font-size:22px; color:#ffffff; font-weight:700;">Pyrolert</h1>'
    )
    headcount_image_html, headcount_inline = _build_headcount_image(
        headcount_image_path,
        headcount_image_url,
    )
    headcount_block = (
        '<p style="font-size:14px; margin:0 0 8px; font-weight:700;">Recent Image Captured</p>'
        f'<div style="margin:0 0 16px;">{headcount_image_html}</div>'
        if headcount_image_html
        else ""
    )
    html_body = f"""
<!DOCTYPE html>
<html lang="en" style="margin:0; padding:0; background-color:#ffffff; font-family: Arial, sans-serif;">
    <head>
        <meta charset="UTF-8" />
        <title>Pyrolert Escalation Notification</title>
    </head>
    <body style="margin:0; padding:0; background-color:#ffffff; font-family: Arial, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#ffffff; padding:32px 0;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff; border-radius:12px; border:1px solid #ececec; overflow:hidden;">
                        <tr>
                                <td align="center" style="background-color:#b00020; padding:20px 28px;">
                                {logo_html}
                            </td>
                        </tr>
                        <tr>
                            <td style="padding:28px; color:#333333;">
                                    <h2 style="font-size:20px; font-weight:600; margin:0 0 12px 0; color:#b00020;">Alert Escalation Notification</h2>
                                        <p style="font-size:15px; margin:0 0 16px 0; line-height:1.6;">
                                            This is an automated notification. The system has turned from <strong>Warning</strong>
                                            to <strong>High Alert</strong>, and the alert has been escalated based on current conditions.
                                            Kindly check the area.
                                </p>
                                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-size:15px; line-height:1.6; margin-bottom:16px;">
                                    <tr><td style="padding:6px 0 0; font-weight:700;">Alert Status:</td></tr>
                                    <tr><td style="padding:0 0 6px;">{status}</td></tr>
                                    <tr><td style="padding:6px 0 0; font-weight:700;">Triggered at:</td></tr>
                                    <tr><td style="padding:0 0 6px;">{triggered_at}</td></tr>
                                    <tr><td style="padding:6px 0 0; font-weight:700;">Escalated to High Alert at:</td></tr>
                                    <tr><td style="padding:0 0 6px;">{escalation_ts}</td></tr>
                                    <tr><td style="padding:6px 0 0; font-weight:700;">Current Headcount Detected:</td></tr>
                                    <tr><td style="padding:0 0 6px;">{headcount}</td></tr>
                                </table>
                                {headcount_block}
                                <p style="font-size:14px; margin:8px 0 0;">Sincerely,<br>Pyrolert Team</p>
                            </td>
                        </tr>
                        <tr>
                            <td style="background-color:#f7f7f7; padding:16px; text-align:center; font-size:12px; color:#888888;">
                                Pyrolert © 2026
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
</html>
"""
    inline_images: list[tuple[str, bytes, str]] = []
    if logo_inline:
        inline_images.append(logo_inline)
    if headcount_inline:
        inline_images.extend(headcount_inline)
    inline_payload = inline_images or None
    try:
        send_message_from_env(to_email, subject, body, html_body, inline_payload)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    _load_env()
    recipient = os.getenv("GMAIL_RECIPIENT")
    if not recipient:
        raise RuntimeError("Missing GMAIL_RECIPIENT environment variable.")
    send_hello_from_env(recipient)
