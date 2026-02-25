from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.accounts.models import UserRole


class Command(BaseCommand):
    help = "Create default user role groups"

    def handle(self, *args, **options):
        for role in UserRole.values:
            group, created = Group.objects.get_or_create(name=role)
            action = "created" if created else "exists"
            self.stdout.write(self.style.SUCCESS(f"{group.name}: {action}"))
