
from django.contrib import admin

from myApp.models import TenantPayment

from .models import TokenPrice, MoversPlan


@admin.register(TokenPrice)
class TokenPriceAdmin(admin.ModelAdmin):
    list_display = ('token_count', 'amount')

@admin.register(TenantPayment)
class TenantPaymentAdmin(admin.ModelAdmin):
    list_display = ('get_tenant_name', 'amount', 'transaction_code', 'timestamp', 'is_approved')
    list_filter = ('is_approved',)
    search_fields = ('tenant__user__username', 'transaction_code')
    list_editable = ('is_approved',)

    def get_tenant_name(self, obj):
        return obj.tenant.user.get_full_name() or obj.tenant.user.username
    get_tenant_name.short_description = 'Tenant'




@admin.register(MoversPlan)
class MoversPlansAdmin(admin.ModelAdmin):
    list_display = ('vehicle_type', 'price')
