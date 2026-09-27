"""`manage.py generate_secrets_key` — a new `DOLPHIN_SECRETS_KEY` value.

Print it into `secrets/.env` as `DOLPHIN_SECRETS_KEY=<value>`. To rotate, put
the new key first and keep the old one after a comma until every secret has
been saved again; see docs/ops/DOLPHIN_DEPLOYMENT_RUNBOOK.md.
"""

from django.core.management.base import BaseCommand

from integrations.crypto import generate_key


class Command(BaseCommand):
    help = "Print a new Fernet key for DOLPHIN_SECRETS_KEY."

    def handle(self, *args, **options):
        self.stdout.write(generate_key())
