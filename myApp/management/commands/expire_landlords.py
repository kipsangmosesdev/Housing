from django.core.management.base import BaseCommand

from myApp.models import registerUser


class Command(BaseCommand):
    help = 'Expires landlords whose latest payment subscription has expired.'

    def handle(self, *args, **kwargs):
        expired_count = 0

        active_landlords = registerUser.objects.filter(is_paid=True)

        for landlord in active_landlords:
            before = landlord.is_paid
            landlord.enforce_subscription_status()
            after = landlord.is_paid

            if before and not after:
                expired_count += 1
                self.stdout.write(self.style.WARNING(
                    f"{landlord.user.email} subscription expired and marked as unpaid."
                ))

        self.stdout.write(self.style.SUCCESS(f"{expired_count} landlord(s) subscription expired successfully."))
