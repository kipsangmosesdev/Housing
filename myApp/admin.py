# Export to csv
import csv
from pyexpat.errors import messages

from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils.html import format_html

from myApp.models import (Amenity, Comment, FavoriteProperty, Payment,
                          Property, PropertyImage, PropertyType, PropertyView,
                          ReferralSubmission, SystemRating, Tenant,
                          registerUser)

# Register your models here.


def export_as_csv(modeladmin, request, queryset):
    """
    Generic CSV export admin action.
    """
    opts = modeladmin.model._meta
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename={opts.verbose_name_plural}.csv'

    writer = csv.writer(response)
    # Write header row
    field_names = [field.name for field in opts.fields]
    writer.writerow(field_names)

    # Write data rows
    for obj in queryset:
        writer.writerow([getattr(obj, field) for field in field_names])

    return response

export_as_csv.short_description = "Export selected to CSV"



@admin.register(PropertyType)
class PropertyTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    actions = [export_as_csv]

@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    actions = [export_as_csv]
    
from django.contrib import admin
from django.db.models import Sum


# custom action
def calculate_total_amount(modeladmin, request, queryset):
    total = queryset.aggregate(total=Sum('amount'))['total'] or 0
    modeladmin.message_user(
        request,
        f" Total Amount of selected payments: {total}",
        level=messages.SUCCESS   # green success alert
    )

calculate_total_amount.short_description = "Calculate total of selected payments"

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'landlord', 
        'amount',
        'phone_number', 
        'mpesa_receipt',
        'status',
        'is_successful', 
        'timestamp', 
        'expiry_date'
    )
    list_filter = (
        'status',
        ('timestamp', admin.DateFieldListFilter),
        ('expiry_date', admin.DateFieldListFilter),
    )
    actions = [export_as_csv, calculate_total_amount]
    search_fields = ('landlord__user__email', 'mpesa_receipt')

    

from django.contrib import admin
from django.utils.html import format_html

from .models import (FAQ, GeneralTip, Payment, TokenWallet, Transporter,
                     TransporterEarnings, TransporterRating,
                     TransporterSubscription, adminUpdate, registerUser)

# from .admin_actions import export_as_csv  # if you have a custom action defined


class PropertyInline(admin.TabularInline):
    model = Property
    extra = 0  # No extra empty forms
    fields = ('landlord', 'title', 'city', 'estate', 'is_available', 'is_approved', 'featured','is_verified')
    readonly_fields = ('landlord', 'title', 'city', 'estate', 'is_available')
    show_change_link = True  # Link to the property change page
    can_delete = True  # Allow deletion from inline

class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ('amount', 'phone_number', 'mpesa_receipt', 'status', 'is_successful', 'timestamp', 'expiry_date')
    readonly_fields = ('amount', 'phone_number', 'mpesa_receipt', 'status', 'is_successful', 'timestamp', 'expiry_date')
    show_change_link = True
    can_delete = False  # prevent deletion from inline

@admin.register(registerUser)
class LandlordAdmin(admin.ModelAdmin):
    list_display = (
        'first_name',
        'id_number',
        'landlord_type',
        'is_paid',
        'is_verified',
        'latest_mpesa_receipt',
        'latest_payment_time',
        'latest_expiry_date',
        'subscription_fee_display',
        'is_free_trial',
        'trial_expiry', 
    )
    list_filter = ('landlord_type','is_verified')
    search_fields = ('user__email', 'id_number')
    actions = [export_as_csv]
    list_editable = ('landlord_type','is_verified')
    readonly_fields = (
        'latest_mpesa_receipt',
        'latest_payment_time',
        'latest_expiry_date',
    )

    inlines = [
        PropertyInline, 
        PaymentInline,
        
    ]  # Inline display of related properties

    def latest_mpesa_receipt(self, obj):
        latest_payment = obj.payments.filter(is_successful=True).order_by('-timestamp').first()
        return latest_payment.mpesa_receipt if latest_payment else "No payment"
    latest_mpesa_receipt.short_description = "Latest M-Pesa Receipt"

    def latest_payment_time(self, obj):
        latest_payment = obj.payments.filter(is_successful=True).order_by('-timestamp').first()
        return latest_payment.timestamp.strftime('%Y-%m-%d %H:%M') if latest_payment else "No payment"
    latest_payment_time.short_description = "Payment Timestamp"

    def latest_expiry_date(self, obj):
        latest_payment = obj.payments.filter(is_successful=True).order_by('-timestamp').first()
        return latest_payment.expiry_date.strftime('%Y-%m-%d %H:%M') if latest_payment and latest_payment.expiry_date else "N/A"
    latest_expiry_date.short_description = "Expiry Date"

    def latest_payment_successful(self, obj):
        latest_payment = obj.payments.order_by('-timestamp').first()
        if latest_payment:
            return "Yes" if latest_payment.is_successful else " No"
        return "No payment"
    latest_payment_successful.short_description = "Payment Successful?"
    
    def subscription_fee_display(self, obj):
        return f"Ksh {obj.subscription_fee()}"
    subscription_fee_display.short_description = "Subscription Fee"


@admin.register(adminUpdate)
class AdminUpdateAdmin(admin.ModelAdmin):
    list_display = ('title', 'date_posted', 'is_active')
    list_filter = ('is_active', 'date_posted')
    list_editable = ('is_active',)
    search_fields = ('title', 'content')
    actions = [export_as_csv]


from .models import SubscriptionPlan


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('landlord_type', 'price')
    list_editable = ('price',)



class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 0  # No extra empty forms
    fields = ('image', 'image_tag')
    readonly_fields = ('image_tag',)
    
    def image_tag(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-width: 100px; max-height:100px;" />', obj.image.url)
        return "No Image"
    image_tag.short_description = 'Image Preview'

class PropertyAmenityInline(admin.TabularInline):
    model = Property.amenities.through  # Through model for ManyToManyField
    extra = 0
    verbose_name = "Amenity"
    verbose_name_plural = "Amenities"
    can_delete = False  # prevent deletion from inline
    show_change_link = True  # Link to the amenity change page

class commentInline(admin.TabularInline):
    model = Comment
    extra = 0
    fields = ('user', 'content', 'timestamp', 'is_approved')
    readonly_fields = ('user', 'content', 'timestamp')
    show_change_link = True
    can_delete = False  # prevent deletion from inline

class PropertyViewInline(admin.TabularInline):
    model = PropertyView
    extra = 0
    fields = ('tenant', 'viewed_on')
    readonly_fields = ('tenant', 'viewed_on')
    show_change_link = True
    can_delete = False  # prevent deletion from inline

class FavoritePropertyInline(admin.TabularInline):
    model = FavoriteProperty
    extra = 0
    fields = ('property', 'added_on')
    readonly_fields = ('property', 'added_on')
    show_change_link = True
    can_delete = False  # prevent deletion from inline
    
@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('landlord', 'title', 'city', 'estate', 'is_available', 'is_approved','is_verified','featured','property_document', 'date_posted')
    list_filter = ('is_available', 'is_approved','is_verified', 'featured', 'city', 'date_posted')
    search_fields = ('title','estate', 'landlord__user__email', 'landlord__id_number')
    actions = [export_as_csv]
    list_editable = ('is_approved','is_verified','featured',)

    inlines = [
        PropertyImageInline, 
        PropertyAmenityInline, 
        commentInline,
        PropertyViewInline,
        FavoritePropertyInline
        ]  # Inline display of related images

class FavoritePropertyInline(admin.TabularInline):
    model = FavoriteProperty
    extra = 0
    fields = ('property', 'added_on')
    readonly_fields = ('property', 'added_on')
    show_change_link = True
    can_delete = False  # prevent deletion from inline

class PropertyViewInline(admin.TabularInline):
    model = PropertyView
    extra = 0
    fields = ('property', 'viewed_on')
    readonly_fields = ('property', 'viewed_on')
    show_change_link = True
    can_delete = False  # prevent deletion from inline


class ReferralSubmissionInline(admin.TabularInline):
    model = ReferralSubmission
    extra = 0
    fields = ('unique_identity_key', 'landlord_name', 'mpesa_receipt', 'is_verified', 'is_paid', 'submitted_at')
    readonly_fields = ('unique_identity_key', 'landlord_name', 'mpesa_receipt', 'is_verified', 'is_paid', 'submitted_at')
    show_change_link = True
    can_delete = False  # prevent deletion from inline
    
@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = (
        'get_first_name',
        'get_last_name',
        'id_number',
        'phone_number',
        'date_joined',
    )
    
    #Use related field lookups for filtering/searching
    list_filter = ('date_joined',)
    search_fields = ('user__first_name', 'user__last_name', 'phone_number', 'id_number')
   

    actions = [export_as_csv]  # Assuming you've defined this elsewhere

    def get_first_name(self, obj):
        return obj.user.first_name
    get_first_name.short_description = 'First Name'

    def get_last_name(self, obj):
        return obj.user.last_name
    get_last_name.short_description = 'Last Name'
    
    inlines = [
        FavoritePropertyInline,
        PropertyViewInline,
        ReferralSubmissionInline
    ]
    
@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'property','content', 'timestamp', 'is_approved')
    list_filter = ('is_approved', 'timestamp')
    search_fields = ('user__username', 'property__title', 'content')
    list_editable = ('is_approved',)  # Allow inline editing in list view
    
    # Optional: custom short content display
    def content_snippet(self, obj):
        return obj.content[:50] + ('...' if len(obj.content) > 50 else '')
    content_snippet.short_description = "Comment"

@admin.register(SystemRating)
class SystemRatingAdmin(admin.ModelAdmin):
    list_display = ('user', 'score','review', 'is_approved', 'timestamp')
    list_filter = ('score', 'is_approved', 'timestamp')
    search_fields = ('user__username', 'review')
    list_editable = ('is_approved',)

from django.contrib import admin

from .models import TokenTransaction, TokenWallet


@admin.register(TokenWallet)
class TokenWalletAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'tokens', 'last_updated')
    search_fields = ('tenant__username', 'tenant__email')
    list_filter = ('tokens', 'last_updated')

@admin.register(TokenTransaction)
class TokenTransactionAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'phone_number', 'tokens_bought', 'amount_paid', 'transaction_status','mpesa_receipt', 'timestamp','expiry_date')
    search_fields = ('tenant__username', 'phone_number','mpesa_receipt')
    list_filter = ('transaction_status', 'timestamp')



from django.contrib import admin

from .models import ReferralSubmission, Tenant


@admin.register(ReferralSubmission)
class ReferralSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        'tenant_display',
        'unique_identity_key', 
        'tenant_phone',
        'landlord_name', 
        'mpesa_receipt', 
        'is_verified', 
        'is_paid', 
        'submitted_at'
    )
    list_filter = ('is_verified', 'is_paid', 'submitted_at')
    search_fields = ('landlord_name', 'mpesa_receipt', 'tenant__user__username', 'tenant__phone_number','unique_identity_key')
    ordering = ('-submitted_at',)
    list_editable = ('is_paid',)

    def tenant_display(self, obj):
        return f"{obj.tenant.user.username} ({obj.tenant.phone_number})"
    tenant_display.short_description = 'Referred By (Tenant)'
    
    
class TransporterEarningsInline(admin.TabularInline):
    model = TransporterEarnings
    extra = 0
    fields = ('location_start', 'destination', 'earned_amount', 'receipt', 'is_paid', 'created_at')
    readonly_fields = ('location_start', 'destination', 'earned_amount', 'receipt', 'is_paid', 'created_at')
    show_change_link = True
    can_delete = False  # prevent deletion from inline

class TransporterSubscriptionInline(admin.TabularInline):
    model = TransporterSubscription
    extra = 0
    fields = ('phone_number', 'amount', 'mpesa_receipt', 'is_paid', 'start_date', 'end_date')
    readonly_fields = ('phone_number', 'amount', 'mpesa_receipt', 'is_paid', 'start_date', 'end_date')
    show_change_link = True
    can_delete = False  # prevent deletion from inline

class TransporterRatingInline(admin.TabularInline):
    model = TransporterRating
    extra = 0
    fields = ('user', 'rating', 'comment', 'created_at')
    readonly_fields = ('user', 'rating', 'comment', 'created_at')
    show_change_link = True
    can_delete = False  # prevent deletion from inline
    
@admin.register(Transporter)
class TransporterAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'id_number','transport_type','verified','active', 'on_trial','transporter_license')
    search_fields = ('full_name', 'id_number', 'transport_type')
    list_filter = ('transport_type', 'verified','active', 'on_trial')
    list_editable = ('verified','active')

    inlines = [
        TransporterSubscriptionInline,
        TransporterEarningsInline,
        TransporterRatingInline,
    ]

@admin.register(TransporterSubscription)
class TransporterSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('transporter','phone_number','amount','mpesa_receipt','is_paid','start_date', 'end_date')
    search_fields = ('transporter__full_name', 'transporter__phone','mpesa_receipt')
    list_filter = ('transporter','is_paid', 'start_date', 'end_date')


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ('question','answer','created_at')
    search_fields = ('question',)
    list_filter = ('created_at',)


@admin.register(GeneralTip)
class GeneralTipAdmin(admin.ModelAdmin):
    list_display = ('tip', 'created_at', 'updated_at')
    search_fields = ('tip',)
    list_filter = ('created_at', 'updated_at')
    
# Customize admin site titles
admin.site.site_header = "XbomaSwift"
admin.site.site_title = "XbomaSwift Admin Portal"
admin.site.index_title = "Welcome to XbomaSwift Admin Panel"



