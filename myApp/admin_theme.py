# myApp/admin_theme.py

from django.contrib.admin import AdminSite

from .models import Payment, registerUser


class CustomAdminSite(AdminSite):
    site_header = "House Rental Management System"
    site_title = "House Rental Admin Portal"
    index_title = "Welcome to the Rental Admin Panel"

    def each_context(self, request):
        context = super().each_context(request)
        context['custom_css'] = 'myApp/css/custom_admin.css'
        return context

#  Create the admin site instance
custom_admin_site = CustomAdminSite(name='custom_admin')

#  Register your models
custom_admin_site.register(registerUser)
custom_admin_site.register(Payment)
