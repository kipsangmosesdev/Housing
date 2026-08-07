from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import TokenWallet

User = get_user_model()

@receiver(post_save, sender=User)
def create_token_wallet(sender, instance, created, **kwargs):
    if created:
        TokenWallet.objects.create(tenant=instance)
