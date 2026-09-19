"""Team operations. Provisioning is invite-only: the team creates tenants.

    uv run python -m rivon.platform.cli provision-tenant \\
        --name "Demo Solar" --slug demo-solar --owner-email owner@example.com

The owner gets a "set your password" email (logged to the console until an
email provider is chosen).
"""

import argparse
import asyncio
import logging
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker

from rivon.config import get_settings
from rivon.db import create_engine
from rivon.platform import auth
from rivon.platform.email import ConsoleEmailSender
from rivon.platform.models import Region


async def _provision(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        tenant = await auth.provision_tenant(
            sessionmaker,
            name=args.name,
            slug=args.slug,
            region=Region(args.region),
            owner_email=args.owner_email,
        )
        await auth.request_password_reset(
            sessionmaker, settings, ConsoleEmailSender(), args.owner_email
        )
    except auth.ProvisioningError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    print(f"tenant {tenant.tenant_id} created; owner {tenant.owner_id} emailed a password link")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rivon")
    commands = parser.add_subparsers(dest="command", required=True)
    provision = commands.add_parser("provision-tenant", help="create a tenant and its owner")
    provision.add_argument("--name", required=True)
    provision.add_argument("--slug", required=True)
    provision.add_argument("--region", choices=[r.value for r in Region], default=Region.EU.value)
    provision.add_argument("--owner-email", required=True)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return asyncio.run(_provision(args))


if __name__ == "__main__":
    sys.exit(main())
