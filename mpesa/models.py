# Create your models here.
from django.db import models


class TokenPrice(models.Model):
    token_count = models.PositiveIntegerField(unique=True)
    amount = models.PositiveIntegerField(help_text="Amount in KES")

    def __str__(self):
        return f"{self.token_count} tokens - KES {self.amount}"

class MoversPlan(models.Model):
    vehicle_type = models.CharField(max_length=100)
    price = models.PositiveIntegerField(help_text="Price in KES")

    class Meta:
        verbose_name = "Movers Plan"
        verbose_name_plural = "Movers Plans"

    def __str__(self):
        return f"{self.vehicle_type} - KES {self.price}"
