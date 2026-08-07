from django.contrib.auth import get_user_model
from django.contrib.auth.views import PasswordResetView

User = get_user_model()

class RoleAwarePasswordResetView(PasswordResetView):
    template_name = 'accounts/password_reset_form.html'
    email_template_name = 'registration/password_reset_email.html'
    subject_template_name = 'registration/password_reset_subject.txt'
    success_url = '/accounts/password-reset/done/'  # optional

    def form_valid(self, form):
        email = form.cleaned_data.get("email")
        try:
            self._target_user = User.objects.get(email=email)  # Save user for context
        except User.DoesNotExist:
            self._target_user = None
        return super().form_valid(form)

    def get_email_context_data(self, **kwargs):
        """Inject extra context into password reset email."""
        context = super().get_email_context_data(**kwargs)
        user = getattr(self, "_target_user", None)

        # Determine role
        if getattr(user, "is_tenant", False):
            role = "tenant"
        elif getattr(user, "is_landlord", False):
            role = "landlord"
        elif getattr(user, "is_transporter", False):
            role = "transporter"
        else:
            role = "User"

        context["user_role"] = role
        context["domain"] = 'www.xbomaswift.com'
        context["protocol"] = "https" if self.request.is_secure() else "http"
        context["expiration_days"] = 1
        return context
