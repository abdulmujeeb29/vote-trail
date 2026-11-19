import secrets

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import Participant


class Command(BaseCommand):
    help = "Create a verified verifier/observer account (password printed once)."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--phone", required=True)
        parser.add_argument("--role", default="verifier", choices=["verifier", "observer"])
        parser.add_argument("--password", default="")

    def handle(self, *args, **o):
        password = o["password"] or secrets.token_urlsafe(12)
        user, _ = User.objects.get_or_create(username=o["username"])
        user.set_password(password)
        user.save()
        p = Participant.objects.filter(user=user).first() or Participant(user=user)
        p.set_phone(o["phone"])
        p.role = o["role"]
        p.verified_at = timezone.now()
        p.save()
        self.stdout.write(self.style.SUCCESS(f"{o['role']} '{user.username}' ready."))
        if not o["password"]:
            self.stdout.write(f"Password: {password}")
