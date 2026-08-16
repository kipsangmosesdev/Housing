import os
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from jsonschema import ValidationError

# Create your models here.

class registerUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    is_free_trial = models.BooleanField(default=True)
    trial_expiry = models.DateTimeField(null=True, blank=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    id_number = models.CharField(max_length=20, unique=True, null=True, blank=False)
    kra_pin = models.CharField(max_length=20, unique=True, null=True, blank=False)
    phone_number = models.CharField(max_length=15)
    landlord_type = models.CharField(max_length=20, choices=[('individual', 'Basic Landlord'), ('company', 'Standard Landlord'), ('agent', 'Premium Landlord/Agent')])
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(auto_now=True)
    is_paid = models.BooleanField(default=False)
    profile_photo = models.ImageField(upload_to='landlord_photos/', blank=True, null=True)
    is_verified = models.BooleanField(default=True)
    
    class Meta:
        ordering = ["-date_joined"]
        verbose_name = "Landlords"
        verbose_name_plural = "Landlords"
    
    def property_limit(self):
        if self.landlord_type == 'individual':
            return 1
        elif self.landlord_type == 'company':
            return 3
        elif self.landlord_type == 'agent':
            return 7
        return 0
    
    # grant the new landlord free 30 days trial on creation
    def save(self, *args, **kwargs):
        if not self.pk and self.is_free_trial:  # Only set on creation
            self.trial_expiry = timezone.now() + timezone.timedelta(days=30)
        super().save(*args, **kwargs)
    
    def subscription_fee(self):
        from .models import SubscriptionPlan  # Local import to prevent circular dependency
        try:
            plan = SubscriptionPlan.objects.get(landlord_type=self.landlord_type)
            return plan.price
        except SubscriptionPlan.DoesNotExist:
                return 0
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.landlord_type})"

    def yearly_subscription_fee(self):
        from .models import YearlySubscriptionPlan  # Local import to prevent circular dependency
        try:
            yearly_plan = YearlySubscriptionPlan.objects.get(landlord_type=self.landlord_type)
            return yearly_plan.price
        except YearlySubscriptionPlan.DoesNotExist:
            return 0
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.landlord_type})"


# Monthly subscription plans for landlords
class SubscriptionPlan(models.Model):
    LANDLORD_TYPES = [
        ('individual', 'Individual (Basic)'),
        ('company', 'Company (Standard)'),
        ('agent', 'Agent (Premium)'),
    ]
    landlord_type = models.CharField(max_length=20, choices=LANDLORD_TYPES, unique=True)
    price = models.PositiveIntegerField(help_text="Monthly subscription fee in KES")
    
    class Meta:
        verbose_name = "Landlord subscription plan"
        verbose_name_plural = "Landlords Monthly plans"

    def __str__(self):
        return f"{self.get_landlord_type_display()} - KES {self.price}"


# Yearly subscription plans for landlords
class YearlySubscriptionPlan(models.Model):
    LANDLORD_TYPES = [
        ('individual', 'Individual (Basic)'),
        ('company', 'Company (Standard)'),
        ('agent', 'Agent (Premium)'),
    ]
    landlord_type = models.CharField(max_length=20, choices=LANDLORD_TYPES, unique=True)
    price = models.PositiveIntegerField(help_text="Yearly subscription fee in KES")
    
    class Meta:
        verbose_name = "Landlord yearly subscription plan"
        verbose_name_plural = "Landlords yearly plans"

    def __str__(self):
        return f"{self.get_landlord_type_display()} - KES {self.price}"

class adminUpdate(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    date_posted = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ["-date_posted"]
        verbose_name = "Admin Updates"
        verbose_name_plural = "Admin Updates"

    def __str__(self):
        return self.title
    
class PropertyType(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name

class Amenity(models.Model):
    name = models.CharField(max_length=200)
    
    class Meta:
        verbose_name = "Amenities"
        verbose_name_plural = "Amenities"

    def __str__(self):
        return self.name

class Location(models.Model):
    county = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    estate = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.estate}, {self.city}, {self.county}"


from django.urls import reverse


from django.db import models
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.urls import reverse
from PIL import Image
from io import BytesIO
import os


# ==============================
# Property Model
# ==============================
class Property(models.Model):
    landlord = models.ForeignKey(
        'registerUser',
        on_delete=models.CASCADE,
        related_name='properties'
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    property_type = models.ForeignKey(
        'PropertyType',
        on_delete=models.SET_NULL,
        null=True
    )
    city = models.CharField(max_length=255)
    estate = models.CharField(max_length=255)
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    address = models.CharField(max_length=255)
    rent = models.DecimalField(max_digits=10, decimal_places=2)
    bedrooms = models.IntegerField()
    bathrooms = models.IntegerField()
    has_balcony = models.BooleanField(default=False)

    # Document field (e.g., proof or deed)
    def validate_image_file(value):
        ext = os.path.splitext(value.name)[1].lower()
        allowed_extensions = ['.jpg', '.jpeg', '.png']
        if ext not in allowed_extensions:
            raise ValidationError('Only .jpg, .jpeg, and .png files are allowed.')

    property_document = models.ImageField(
        upload_to='property_documents/',
        validators=[validate_image_file],
        blank=True,null=False)

    is_approved = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    featured = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)
    date_posted = models.DateTimeField(auto_now_add=True)
    amenities = models.ManyToManyField('Amenity', blank=True)

    class Meta:
        ordering = ["-date_posted"]
        verbose_name = "Rental"
        verbose_name_plural = "Rentals"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('property_detail', kwargs={'pk': self.id})

    # --- Auto Compress Property Document ---
    def save(self, *args, **kwargs):
        if self.property_document:
            img = Image.open(self.property_document)

            # Remove EXIF metadata (saves space)
            img.info.pop('exif', None)

            # Convert to JPEG (RGB only)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Resize if too large (max 1024x1024)
            max_size = (1024, 1024)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

            output = BytesIO()
            quality = 80  # start slightly lower
            img.save(output, format='JPEG', quality=quality, optimize=True)
            data = output.getvalue()

            # Iteratively reduce until <= 90 KB
            target_size_kb = 90
            while len(data) > target_size_kb * 1024 and quality > 25:
                output = BytesIO()
                quality -= 5
                img.save(output, format='JPEG', quality=quality, optimize=True)
                data = output.getvalue()

            # Save the optimized image (flat path)
            base_name = os.path.basename(self.property_document.name)
            file_root, _ = os.path.splitext(base_name)
            new_name = f"{file_root}.jpg"

            self.property_document.save(
                new_name,
                ContentFile(data),
                save=False
            )

        super().save(*args, **kwargs)


# ==============================
# Property Image Model (Gallery)
# ==============================
class PropertyImage(models.Model):
    property = models.ForeignKey(
        'Property',
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(upload_to='property_images/', max_length=255)
    thumbnail = models.ImageField(upload_to='property_thumbnails/', blank=True, null=True, max_length=255)
    caption = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "Rental Image"
        verbose_name_plural = "Rental Images"

    def __str__(self):
        return f"Image for {self.property.title}"

    def save(self, *args, **kwargs):
        """
        Compress uploaded images down to ~90 KB
        and create a small thumbnail (200x200).
        """
        if self.image:
            img = Image.open(self.image.file)
            img.info.pop('exif', None)

            # Convert transparent PNGs to RGB JPEG
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Resize main photo (max 1024x1024 for consistent quality)
            max_size = (1024, 1024)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

            output = BytesIO()
            quality = 80
            img.save(output, format='JPEG', quality=quality, optimize=True)
            data = output.getvalue()

            # Compress until around 90 KB
            target_size_kb = 90
            while len(data) > target_size_kb * 1024 and quality > 25:
                output = BytesIO()
                quality -= 5
                img.save(output, format='JPEG', quality=quality, optimize=True)
                data = output.getvalue()

            # Ensure path doesn't recursively build
            base_name = os.path.basename(self.image.name)
            file_root, _ = os.path.splitext(base_name)
            new_filename = f"{file_root}.jpg"

            self.image.save(new_filename, ContentFile(data), save=False)

            # --- Create Thumbnail (200x200) ---
            thumb_io = BytesIO()
            thumb = img.copy()
            thumb.thumbnail((200, 200), Image.Resampling.LANCZOS)
            thumb.save(thumb_io, format='JPEG', quality=70, optimize=True)

            thumb_name = f"thumb_{new_filename}"
            self.thumbnail.save(thumb_name, ContentFile(thumb_io.getvalue()), save=False)

        super().save(*args, **kwargs)



from datetime import timedelta

from django.db import models
from django.utils import timezone


from django.db import models
from django.utils import timezone
from datetime import timedelta

class Payment(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Success', 'Success'),
        ('Failed', 'Failed'),
    ]

    SUBSCRIPTION_TYPE_CHOICES = [
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]

    landlord = models.ForeignKey('registerUser', on_delete=models.CASCADE, related_name='payments')
    plan = models.ForeignKey(
        'SubscriptionPlan', on_delete=models.CASCADE, related_name='payments', null=True, blank=True
    )
    # Replaced yearly_plan foreign key with a clean structural type choice field
    subscription_type = models.CharField(
        max_length=10, 
        choices=SUBSCRIPTION_TYPE_CHOICES, 
        default='monthly'
    )
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    phone_number = models.CharField(max_length=13)  # Format: '2547...'
    transaction_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    mpesa_receipt = models.CharField(max_length=100, null=True, blank=True)
    checkout_request_id = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    is_successful = models.BooleanField(default=False)
    timestamp = models.DateTimeField(default=timezone.now)
    expiry_date = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # Sync is_successful boolean with status choices
        if self.status == 'Success':
            self.is_successful = True
            # Dynamically calculate expiry dates upon transition to successful
            if not self.expiry_date:
                if self.subscription_type == 'yearly':
                    self.expiry_date = self.timestamp + timedelta(days=365)
                else:
                    self.expiry_date = self.timestamp + timedelta(days=30)
        else:
            self.is_successful = False

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.landlord} - {self.amount} KES ({self.get_subscription_type_display()}) on {self.timestamp.strftime('%Y-%m-%d')}"

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Landlord Subscription"
        verbose_name_plural = "Landlords Subscriptions"
        
        indexes = [
            models.Index(fields=['checkout_request_id']),
            models.Index(fields=['transaction_id']),
            models.Index(fields=['landlord']),
        ]

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Tenant(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=20)
    id_number = models.CharField(max_length=20, unique=True)
    kra_pin = models.CharField(max_length=20, unique=True, null=True, blank=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    is_subscribed = models.BooleanField(default=False)
    subscription_expires = models.DateTimeField(null=True, blank=True)
    mpesa_receipt = models.CharField(max_length=100, null=True, blank=True)
    show_neaby_house = models.BooleanField(default=True)
    
    class Meta:
        ordering = ["-date_joined"]
        verbose_name = "Tenants"
        verbose_name_plural = "Tenants"

    def is_subscription_active(self):
        return bool(self.subscription_expires and self.subscription_expires > timezone.now())

# Model for Favorites
class FavoriteProperty(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    property = models.ForeignKey(Property, on_delete=models.CASCADE)
    added_on = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-added_on"]
        verbose_name = "Tenants favorites"
        verbose_name_plural = "Tenants favorites"
        
        unique_together = ('tenant', 'property')  # prevent duplicates
        
    def __str__(self):
        return f"{self.tenant.user.username} -> {self.property.title}"


# Recent property 
class PropertyView(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    property = models.ForeignKey(Property, on_delete=models.CASCADE)
    viewed_on = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('tenant', 'property')
        ordering = ['-viewed_on']
        
        verbose_name = "Views"
        verbose_name_plural = "Views"

    def __str__(self):
        return f"{self.tenant.user.username} viewed {self.property.title}"


# TenantPayment model

class TenantPayment(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    transaction_code = models.CharField(max_length=100, unique=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.tenant.user.username} - {self.transaction_code}"
    
    
class Comment(models.Model):
    property = models.ForeignKey('Property', on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=False) 

    def __str__(self):
        return f"{self.user.username} - {self.property.title[:30]}"


from django.contrib.auth.models import User
# Ratings
from django.db import models

from .models import Property  # adjust if needed


class Rating(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='ratings')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    score = models.IntegerField(choices=[(i, i) for i in range(1, 6)])
    review = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        unique_together = ('property', 'user')  # one rating per user per property

    def __str__(self):
        return f"{self.user.username} - {self.score}★ for {self.property.title}"


# System ratings
class SystemRating(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)  # Ensures one rating per user
    score = models.IntegerField(choices=[(i, i) for i in range(1, 6)])
    review = models.TextField(blank=True, null=True)
    is_approved = models.BooleanField(default=False)  # Optional: if you want admin moderation
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
    def __str__(self):
        return f"{self.user.username} - {self.score}★"


from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class TokenWallet(models.Model):
    tenant = models.OneToOneField(User, on_delete=models.CASCADE)
    tokens = models.PositiveIntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)  # Tracks when tokens were last changed

    class Meta:
        verbose_name = "Swift wallet"
        verbose_name_plural = "Swift wallets"

    def __str__(self):
        return f"{self.tenant.username} - Tokens: {self.tokens}"

    def use_token(self):
        """
        Deduct one token when a tenant uses a feature that requires it.
        """
        if self.tokens >= 1:
            self.tokens -= 1
            self.save()
            return True
        return False

    import logging
    from django.utils import timezone

    logger = logging.getLogger(__name__)

    def expire_tokens(self):
        """
        Deduct expired tokens from the tenant's wallet safely.
        This should be called periodically (via cron/Celery) or on wallet access.
        """
        from myApp.models import TokenTransaction
        import logging

        now = timezone.now()  # Use UTC-safe time comparison
        total_expired = 0

        # Fetch all unprocessed, expired successful transactions
        expired_transactions = TokenTransaction.objects.filter(
            tenant=self.tenant,
            transaction_status='Success',
            expiry_date__lte=now,
            processed_expiry=False
        ).order_by('expiry_date')

        if not expired_transactions.exists():
            self.logger.info(f"[Token Expiry] No expired tokens for {self.tenant.username}")
            return 0

        for tx in expired_transactions:
            try:
                # Double-check expiry to prevent race conditions
                if tx.expiry_date and tx.expiry_date <= now and not tx.processed_expiry:
                    tokens_to_deduct = min(self.tokens, tx.tokens_bought)

                    if tokens_to_deduct > 0:
                        self.tokens -= tokens_to_deduct
                        total_expired += tokens_to_deduct

                        self.logger.info(
                            f"[Token Expiry] {self.tenant.username}: "
                            f"Expired {tokens_to_deduct} tokens from TX#{tx.id}"
                        )

                    # Mark this transaction as processed
                    tx.processed_expiry = True
                    tx.save(update_fields=['processed_expiry'])

            except Exception as e:
                self.logger.error(
                    f"[Token Expiry] Error expiring TX#{tx.id} for {self.tenant.username}: {e}"
                )
                continue
        
        logger = logging.getLogger('myApp.token_expiry')
        logger.info(f"[Token Expiry] {self.tenant.username}: {total_expired} tokens expired.")
        # Save wallet once after all deductions
        if total_expired > 0:
            self.save(update_fields=['tokens'])
            self.logger.info(
                f"[Token Expiry] Total {total_expired} tokens expired for {self.tenant.username}"
            )
        else:
            self.logger.info(f"[Token Expiry] No tokens deducted for {self.tenant.username}")

        return total_expired



from datetime import timedelta

from django.db import models
from django.utils import timezone


class TokenTransaction(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Success', 'Success'),
        ('Failed', 'Failed'),
    ]
    
    tenant = models.ForeignKey(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=13)
    tokens_bought = models.PositiveIntegerField()
    amount_paid = models.PositiveIntegerField()
    mpesa_receipt = models.CharField(max_length=100, null=True, blank=True)
    checkout_request_id = models.CharField(max_length=100, null=True, blank=True)
    transaction_status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='Pending'
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateTimeField(null=True, blank=True)  # NEW field
    processed_expiry = models.BooleanField(default=False)


    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Swift transactions"
        verbose_name_plural = "Swift transactions"

    def __str__(self):
        return f"{self.tenant.username} bought {self.tokens_bought} tokens"

    def save(self, *args, **kwargs):
        """
        Automatically credits tokens and sets expiry when payment succeeds.
        """
        old_status = None
        if self.pk:
            old_status = TokenTransaction.objects.get(pk=self.pk).transaction_status

        # Run the normal save
        super().save(*args, **kwargs)

        # Credit tokens and set expiry only once when payment succeeds
        if self.transaction_status == 'Success' and old_status != 'Success':
            wallet, _ = TokenWallet.objects.get_or_create(tenant=self.tenant)
            wallet.tokens += self.tokens_bought
            wallet.save()

            # Set expiry date to 2 hours for 1 token, 1 day for 3 tokens, 2 days for 5 tokens,
            # 7 days for 10 tokens and 14 days for 15 tokens
            if self.tokens_bought == 1:
                self.expiry_date = timezone.now() + timedelta(hours=2)
            elif self.tokens_bought == 3:
                self.expiry_date = timezone.now() + timedelta(days=1)
            elif self.tokens_bought == 5:
                self.expiry_date = timezone.now() + timedelta(days=2)
            elif self.tokens_bought == 10:
                self.expiry_date = timezone.now() + timedelta(days=7)
            elif self.tokens_bought == 15:
                self.expiry_date = timezone.now() + timedelta(days=14)
            super().save(update_fields=['expiry_date'])

    @classmethod
    def expire_unused_tokens(cls):
        """
        Go through all successful transactions whose tokens have expired,
        and remove unused tokens from the wallet.
        This can be run periodically (e.g. via cron or Celery beat).
        """
        expired_transactions = cls.objects.filter(
            transaction_status='Success',
            expiry_date__lte=timezone.now()
        )

        for tx in expired_transactions:
            wallet, _ = TokenWallet.objects.get_or_create(tenant=tx.tenant)
            if wallet.tokens >= tx.tokens_bought:
                wallet.tokens -= tx.tokens_bought
                wallet.save()
                print(f"Expired {tx.tokens_bought} tokens for {tx.tenant.username}")



from django.db import models


class ReferralSubmission(models.Model):
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, related_name='referrals')
    landlord_name = models.CharField(max_length=100)
    landlord_phone = models.CharField(max_length=15)
    tenant_phone = models.CharField(max_length=15)
    mpesa_receipt = models.CharField(max_length=20, unique=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=False)
    unique_identity_key = models.CharField(max_length=255, editable=False, unique=True)
    
    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = 'Referrals'
        verbose_name_plural = 'Referrals'

    def save(self, *args, **kwargs):
        # Set the identity key before saving
        self.unique_identity_key = f"{self.landlord_name.strip().lower()}_{self.tenant.id}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.tenant.user.username} referred {self.landlord_name}"


# Transporter model
class Transporter(models.Model):
    TRANSPORT_TYPE_CHOICES = [
        ('pickup', 'Pickup'),
        ('canter', 'Canter'),
        ('lorry', 'Lorry'),
        ('truck', 'Truck'),
        ('trailer', 'Trailer'),   
    ]
    
    CAPACITY_TYPE_CHOICES = [
        ('tonnes', 'Tonnes'),
        ('weight', 'Kgs'),
        ('volume','liters')
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)  # Transporter account
    on_trial = models.BooleanField(default=True)
    trial_expiry = models.DateTimeField(null=True, blank=True)
    full_name = models.CharField(max_length=100)
    id_number = models.CharField(max_length=20, unique=True)
    kra_pin = models.CharField(max_length=20, unique=True, null=True, blank=False)
    phone = models.CharField(max_length=20)
    email = models.EmailField(unique=True, blank=False, null=False)
    city = models.CharField(max_length=100)
    address = models.CharField(max_length=150)
    transport_type = models.CharField(max_length=20, choices=TRANSPORT_TYPE_CHOICES)
    vehicle_name = models.CharField(max_length=100, blank=True, help_text="E.g. Toyota Pick-up")
    capacity_type = models.CharField(max_length=10, choices=CAPACITY_TYPE_CHOICES)
    vehicle_capacity = models.PositiveIntegerField()
    vehicle_plate = models.CharField(max_length=20)
    description = models.TextField(help_text="E.g. route description...")
    vehicle_image = models.ImageField(upload_to="transporters/", blank=True, null=True)
    transporter_license = models.ImageField(upload_to="transporter_licenses/", blank=True, null=True)
    national_id_image = models.ImageField(upload_to="transporter_ids/", blank=False, null=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    online = models.BooleanField(default=True)
    active = models.BooleanField(default=False)
    verified = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-created_at"]

   
    def save(self, *args, **kwargs):
        from PIL import Image
        from io import BytesIO
        from django.core.files.base import ContentFile
        from django.utils import timezone
        import os

        def compress_image(image_field):
            """Compress an image field to around 80KB."""
            if image_field:
                img = Image.open(image_field)
                img.info.pop('exif', None)

                # Convert to RGB if necessary
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

                # Resize large images
                max_size = (1024, 1024)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)

                # Start compression
                output = BytesIO()
                quality = 80
                img.save(output, format='JPEG', quality=quality, optimize=True)
                data = output.getvalue()

                # Iteratively reduce quality until target size is reached
                target_size_kb = 80
                while len(data) > target_size_kb * 1024 and quality > 25:
                    output = BytesIO()
                    quality -= 5
                    img.save(output, format='JPEG', quality=quality, optimize=True)
                    data = output.getvalue()

                # Replace original image
                base_name = os.path.basename(image_field.name)
                file_root, _ = os.path.splitext(base_name)
                new_name = f"{file_root}.jpg"

                image_field.save(
                    new_name,
                    ContentFile(data),
                    save=False
                )

        # --- Compress all images before saving ---
        if self.vehicle_image:
            compress_image(self.vehicle_image)
        if self.transporter_license:
            compress_image(self.transporter_license)
        if self.national_id_image:
            compress_image(self.national_id_image)

        # --- Set free trial on account creation ---
        if not self.pk and getattr(self, 'on_trial', False):
            self.trial_expiry = timezone.now() + timezone.timedelta(days=30)

        # --- Finally, call the parent save ---
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} - {self.vehicle_name}"


# Transporter Subscription model
# models.py
from django.db import models

class TransporterSubscription(models.Model):
    VEHICLE_CHOICES = [
        ('truck', 'Truck'),
        ('pickup', 'Pickup'),
        ('canter', 'Canter'),
        ('lorry', 'Lorry'),
        ('trailer', 'Trailer')
    ]

    transporter = models.ForeignKey("Transporter", on_delete=models.CASCADE)
    checkout_request_id = models.CharField(max_length=100, unique=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    mpesa_receipt = models.CharField(max_length=50, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_paid = models.BooleanField(default=False)
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_CHOICES)
    
    class Meta:
        ordering = ["-created_at"]
    def __str__(self):
        return f"{self.transporter} - {self.vehicle_type} - {self.amount}"
    


# Transporter Rating model
class TransporterRating(models.Model):
    transporter = models.ForeignKey(Transporter, on_delete=models.CASCADE, related_name='ratings')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
    def __str__(self):
        return f"Rating for {self.transporter} by {self.user}"
    
    
class TransporterEarnings(models.Model):
    transporter = models.ForeignKey("Transporter", on_delete=models.CASCADE, related_name="earnings")
    location_start = models.CharField(max_length=100)
    destination = models.CharField(max_length=100)
    earned_amount = models.DecimalField(max_digits=10, decimal_places=2)  # better for money
    receipt = models.CharField(max_length=50, null=True)
    is_paid = models.BooleanField(default=True)  # safer default
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Transporter Earning"
        verbose_name_plural = "Transporter Earnings"

    def __str__(self):
        return f"{self.transporter} | {self.earned_amount} | {self.destination}"
    


# FAQs model
from django.db import models
from django.utils import timezone


class FAQ(models.Model):
    question = models.CharField(max_length=255, unique=True)
    answer = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question

# General tips model
class GeneralTip(models.Model):
    tip = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
        
    class Meta:
        ordering = ['-created_at']
        verbose_name = "General Tip"
        verbose_name_plural = "General Tips"
    