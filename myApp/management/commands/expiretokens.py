from django.core.management.base import BaseCommand
from django.utils import timezone
from myApp.models import TokenTransaction, TokenWallet


class Command(BaseCommand):
    help = "Automatically expire tokens that are older than 60 days."

    def handle(self, *args, **options):
        self.stdout.write("🔍 Starting token expiry process...")

        # Fetch all successful transactions whose expiry date has passed
        expired_transactions = TokenTransaction.objects.filter(
            transaction_status='Success',
            expiry_date__lte=timezone.now()
        )

        if not expired_transactions.exists():
            self.stdout.write(self.style.SUCCESS("✅ No expired tokens found."))
            return

        total_expired = 0
        total_skipped = 0

        for tx in expired_transactions:
            wallet, _ = TokenWallet.objects.get_or_create(tenant=tx.tenant)

            # Ensure no negative token balances
            tokens_to_expire = min(wallet.tokens, tx.tokens_bought)

            if tokens_to_expire > 0:
                wallet.tokens -= tokens_to_expire
                wallet.save()

                # Mark transaction as expired
                tx.transaction_status = 'Expired'
                tx.save(update_fields=['transaction_status'])

                total_expired += tokens_to_expire
                self.stdout.write(
                    self.style.WARNING(
                        f"⏳ Expired {tokens_to_expire} tokens for {tx.tenant.username} "
                        f"(Transaction ID: {tx.id})"
                    )
                )
            else:
                total_skipped += 1
                self.stdout.write(
                    self.style.NOTICE(
                        f"⚠️ Skipped {tx.tenant.username}: no tokens available to expire."
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Token expiry completed. Total expired: {total_expired} | Skipped: {total_skipped}"
            )
        )
