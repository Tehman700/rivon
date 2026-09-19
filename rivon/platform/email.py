"""Outgoing email. The provider is not chosen yet, so only a console backend
exists; a real EU provider becomes another `EmailSender`."""

import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger("rivon.email")


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    async def send(self, email: Email) -> None: ...


class ConsoleEmailSender:
    """Development only: writes the email to the log instead of sending it.
    Emails can contain secrets such as reset links, so never use in production."""

    async def send(self, email: Email) -> None:
        logger.info("email to=%s subject=%s\n%s", email.to, email.subject, email.body)
