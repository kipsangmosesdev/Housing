from django.urls import path

from . import views

urlpatterns = [
    path('service-worker.js', views.service_worker, name='service_worker'),
    
    # Public Pages
    path('', views.tenant_landing_page, name='tenant_landing'),
    path('home/', views.home, name='home'),
    path('property_map/', views.property_map_view, name='property_map'),
    path('help/', views.help_guide, name='help_guide'),
    path('privacy_policy/', views.privacy_policy, name='privacy_policy'),
    path('about_us/', views.about_us, name='about_us'),

    # Landlord Authentication
    path('login', views.unified_login, name='unified_login'),
    path('logout/', views.logout_user, name='logout'),
    path('register/', views.register_landlord, name='register'),
    path('tenant_landlord/', views.landlord_tenant_signup, name='landlord_tenant'),

    # Landlord Dashboard & Profile
    path('dashboard/', views.landlord_dashboard, name='landlord_dashboard'),
    path('dashboard/profile/', views.landlord_profile, name='landlord_profile'),
    path('dashboard/profile/edit/', views.edit_landlord_profile, name='edit_landlord_profile'),
    path('dashboard/profile/confirm-email/<str:token>/', views.confirm_new_email, name='confirm_email'),
    path('dashboard/subscription/', views.landlord_subscription, name='landlord_subscription'),

    # Landlord Payments & Invoices
    path('dashboard/payment/', views.payment_page, name='payment_page'),
    path('dashboard/my-invoices/', views.landlord_invoice_list, name='invoice_list'),
    path('dashboard/invoice/<int:payment_id>/', views.invoice_view, name='invoice_view'),
    path('login/', views.unified_login, name='login'),

    # Property Management (ORDER MATTERS!)
    path('dashboard/new_property', views.post_property, name='new_property'),
    path('dashboard/my_properties/', views.my_properties, name='my_properties'),
    path('dashboard/property/<int:pk>/edit/', views.edit_property, name='edit_property'),
    path('dashboard/property/<int:pk>/delete/', views.delete_property, name='delete_property'),
    path('dashboard/property/<int:pk>/contact/', views.contact_landlord, name='contact_landlord'),
    path('dashboard/property/<int:pk>/', views.property_detail, name='property_detail'),  # Keep last among these

    # Tenant Authentication & Dashboard
    path('tenant/register/', views.tenant_register, name='tenant_register'),
    # path('tenant/login/', views.tenant_login, name='tenant_login'),
    path('tenant/logout/', views.tenant_logout, name='tenant_logout'),
    path('tenant/dashboard/', views.tenant_dashboard, name='tenant_dashboard'),

    # Tenant Favorites
    path('tenant/favorite/<int:pk>/', views.add_favorite, name='add_favorite'),
    path('tenant/unfavorite/<int:pk>/', views.remove_favorite, name='remove_favorite'),

    #Tenant Subscriptions
    path('tenant/subscribe/', views.tenant_subscription_page, name='tenant_subscription_page'),
    path('tenant/mpesa-subscribe/', views.tenant_mpesa_subscription, name='tenant_mpesa_subscription'),
    path('tenant/activate/<int:tenant_id>/', views.manually_activate_subscription, name='manually_activate_subscription'),
    
    path('terms/', views.terms_conditions, name='terms_conditions'),
    path('load-more-properties/', views.load_more_properties, name='load_more_properties'),
    path('api/nearby-properties/', views.nearby_properties_api, name='nearby_properties_api'),
    path('tenant/rate-system/', views.rate_system, name='rate_system'),
    path('tenant/buy_swifts/', views.buy_tokens, name='buy_tokens'),
    path('tenant/swift-history/', views.token_history, name='token_history'),
    path('tenant/<int:pk>/comments/', views.tenant_comments, name='tenant_comments'),
    path('tenant/refer/', views.submit_referral, name='submit_referral'),
    path('user/change_password/', views.change_password, name='change_password'),
    path('transporter/register/', views.register_transporter, name='register_transporter'),
    path('transporter/dashboard/', views.transporter_dashboard, name='transporter_dashboard'),
    path('transporter/profile/edit/', views.edit_transporter_profile, name='edit_transporter_profile'),
    path('transporter/map/', views.transporter_map, name='transporter_map'),
    path('transporters/<int:transporter_id>/', views.transporter_details, name='transporter_details'),
    path('transporters/vehicle-filters/', views.vehicle_filters, name='vehicle_filters'),
    path('search/', views.search, name='search'),
    path('dashboard/transporter-payments/', views.payment_history_list, name='transporter_payment_history'),
    path("transporter/<int:transporter_id>/", views.rate_transporter, name="rate_transporter"),
    path("transporter/<int:transporter_id>/ratings/", views.all_transporter_ratings, name="all_transporter_ratings"),
    path("transporter/",views.add_transporter_earnings, name='add_transporter_earnings'),
    path("transporter/earnings/",views.transporter_earnings_list, name='transporter_earnings_list'),
    path("faqs/", views.faq_list, name="faq_list"),
    path("faqs/add/", views.add_faq, name="add_faq"),
    path("nearby-vehicles/", views.nearby_vehicles_map, name="nearby_vehicles_map"),
    path("ai-agent/", views.ai_agent, name="ai_agent"),
    path("Chat/", views.chat_page, name="chat_page"),
    path("refund/", views.refund_policy, name="refund_policy"),
    path("help-ai/", views.help_ai, name="help_ai"),
    path('pricing/', views.pricing, name='pricing'),
    path('mover-pricing/', views.mover_pricing, name='mover_pricing'),
    path('tenant/profile/', views.tenant_profile, name='tenant_profile'),
    path('tenant/profile/edit/', views.edit_tenant_profile, name='edit_tenant_profile'),
    path('mover-policy/', views.mover_policy, name='mover_policy'),
    path('support/', views.support, name='support'),

   ]

