
from django.urls import path

from . import views

app_name = 'mpesa'

urlpatterns = [
    path('buy/', views.buy_token, name='buy_token'),
    path('callback/', views.mpesa_callback, name='mpesa_callback'),
    path('tenant_pay_only/', views.tenant_pay_only, name='tenant_pay_only'),
    path('dashboard/pay/', views.landlord_payment_view, name='landlord_payment'),
    path('subscribe_transporter/', views.transporter_subscribe_view, name='transporter_subscribe_view'),
]
