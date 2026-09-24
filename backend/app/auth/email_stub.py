"""Credential delivery for invited users -- stubbed for the prototype.

Plumbed as a real function with a real call site (POST /admin/invite
calls this unconditionally after creating an invited user) so swapping
in a real provider (SES, SendGrid, SMTP, ...) later is a one-function
change -- nothing else in the invite flow needs to know delivery is
fake today.

For now: logs what *would* have been sent and returns a result that
POST /admin/invite's response surfaces to the admin, who copies
`temporary_password` and shares it with the invited user out-of-band --
exactly the flow asked for: "the admin would simply copy the creds and
share with the user."
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger("paigs.email_stub")


@dataclass
class EmailDeliveryResult:
    to: str
    subject: str
    delivered: bool
    note: str


def send_invitation_email(to_email: str, temporary_password: str, role: str) -> EmailDeliveryResult:
    subject = "You've been invited to PAIGS WildID"
    logger.info(
        "STUB EMAIL -- to=%s subject=%r role=%s temporary_password=%s "
        "(no real email provider is wired up in this prototype)",
        to_email,
        subject,
        role,
        temporary_password,
    )
    return EmailDeliveryResult(
        to=to_email,
        subject=subject,
        delivered=False,
        note=(
            "Email delivery is stubbed for this prototype -- no message was "
            "actually sent. Copy `temporary_password` from this response and "
            "share it with the invited user directly."
        ),
    )
