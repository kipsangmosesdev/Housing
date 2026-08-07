from django.core.management.base import BaseCommand
from django.utils import timezone

from myApp.models import Tenant


class Command(BaseCommand):
    help = 'Expires tenants whose subscription has expired.'

    def handle(self, *args, **kwargs):
        now = timezone.now()
        expired_tenants = Tenant.objects.filter(is_subscribed=True, subscription_expires__lt=now)

        count = expired_tenants.update(is_subscribed=False)
        self.stdout.write(self.style.SUCCESS(f'{count} tenant(s) subscription expired successfully.'))
