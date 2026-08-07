from datetime import timedelta, timezone

from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import (Property, PropertyImage, ReferralSubmission, SystemRating,
                     Tenant, TenantPayment, Transporter, TransporterEarnings,
                     TransporterRating, TransporterSubscription, registerUser)

# -------------------------------
# 1. Landlord User Registration Form
# -------------------------------


class LandlordUserForm(forms.ModelForm):
    """
    A registration form for landlord users extending the default Django User model.
    Includes custom fields and validation for password confirmation and terms agreement.
    """

    # Personal Info Fields
    first_name = forms.CharField(
        label='First Name',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter first name'
        })
    )

    last_name = forms.CharField(
        label='Last Name',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter last name'
        })
    )

    # Login Credentials
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter password'
        })
    )

    confirm_password = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm password'
        })
    )

    # Terms Agreement
    agree_to_terms = forms.BooleanField(
        label='I agree to the Terms and Conditions',
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your username'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your email'
            }),
        }

    def clean(self):
        """
        Custom validation to ensure passwords match.
        """
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm = cleaned_data.get('confirm_password')

        if password and confirm and password != confirm:
            self.add_error('confirm_password', 'Passwords do not match.')

        return cleaned_data



# -------------------------------
# 2. Landlord Profile Form
# -------------------------------
from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class LandlordUserForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Enter password',
            'class': 'form-control',
            'autocomplete': 'new-password'
        }),
        label="Password",
        help_text="Password must be at least 8 characters long."
    )
    
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Confirm password',
            'class': 'form-control',
            'autocomplete': 'new-password'
        }),
        label="Confirm Password"
    )
    
    agree_to_terms = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        label="I agree to the terms and conditions"
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password']
        widgets = {
            'username': forms.TextInput(attrs={
                'placeholder': 'Username',
                'class': 'form-control',
                'autocomplete': 'username'
            }),
            'email': forms.EmailInput(attrs={
                'placeholder': 'Email address',
                'class': 'form-control',
                'autocomplete': 'email'
            }),
        }
        labels = {
            'username': 'Username',
            'email': 'Email Address',
        }
        help_texts = {
            'username': 'Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.',
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError("Email is already in use.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match.")


class LandlordProfileForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add form-control class to all fields automatically
        for field in self.fields:
            if field != 'profile_photo':
                self.fields[field].widget.attrs.update({'class': 'form-control'})

    class Meta:
        model = registerUser
        fields = [
            'first_name',
            'last_name',
            'id_number',
            'kra_pin',
            'phone_number',
            'landlord_type',
            'profile_photo',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={
                'placeholder': 'First name',
            }),
            'last_name': forms.TextInput(attrs={
                'placeholder': 'Last name',
            }),
            'id_number': forms.TextInput(attrs={
                'placeholder': 'ID number',
                'pattern': '[0-9]*',
                'inputmode': 'numeric'
            }),
            'kra_pin': forms.TextInput(attrs={
                'placeholder': 'KRA PIN',
            }),
            'phone_number': forms.TextInput(attrs={
                'placeholder': '07XXXXXXXX or 01XXXXXXXX',
                'pattern': '[0-9]{10}',
                'inputmode': 'tel'
            }),
            'landlord_type': forms.Select(attrs={
                'class': 'form-select'
            }),
            'profile_photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }
        labels = {
            'first_name': 'First Name',
            'last_name': 'Last Name',
            'id_number': 'ID Number',
            'kra_pin': 'KRA PIN',
            'phone_number': 'Phone Number',
            'landlord_type': 'Type of Landlord',
            'profile_photo': 'Profile Photo',
        }
        help_texts = {
            'phone_number': '10 digits starting with 07 or 01 (e.g., 0712345678 or 0112345678)',
            'profile_photo': 'Upload a clear photo of yourself (optional)',
        }

    def clean_phone_number(self):
        phone = self.cleaned_data['phone_number']
        valid_prefixes = ("07", "01")

        if not phone.isdigit() or len(phone) != 10:
            raise ValidationError("Phone number must be 10 digits long (e.g., 0712345678 or 0112345678).")

        if not phone.startswith(valid_prefixes):
            raise ValidationError("Phone number must start with 07 or 01.")

        return phone

    def clean_id_number(self):
        id_number = self.cleaned_data['id_number']
        if not id_number.isdigit():
            raise ValidationError("ID number must contain only digits.")
        return id_number

    # Validate rent
    def clean_rent(self):
        rent = self.cleaned_data.get('rent')
        if rent is not None and rent <= 0:
            raise ValidationError("Rent must be greater than 0.")
        return rent

    # Validate bedrooms
    def clean_bedrooms(self):
        bedrooms = self.cleaned_data.get('bedrooms')
        if bedrooms is not None and bedrooms < 0:
            raise ValidationError("Bedrooms cannot be negative.")
        return bedrooms

    # Validate bathrooms
    def clean_bathrooms(self):
        bathrooms = self.cleaned_data.get('bathrooms')
        if bathrooms is not None and bathrooms < 0:
            raise ValidationError("Bathrooms cannot be negative.")
        return bathrooms

    # Validate image size (optional but recommended)
    def clean_property_document(self):
        image = self.cleaned_data.get('property_document')
        if image:
            if image.size > 5 * 1024 * 1024:  # 5MB limit
                raise ValidationError("The image size should not exceed 5MB.")
        return image


class PropertyImageForm(forms.ModelForm):
    class Meta:
        model = PropertyImage
        fields = ['image', 'caption']
PropertyImageFormSet = forms.modelformset_factory(PropertyImage, form=PropertyImageForm, extra=3, can_delete=False)
        

class EditLandlordProfileForm(forms.ModelForm):
    class Meta:
        model = registerUser
        fields = ['first_name', 'last_name', 'phone_number', 'profile_photo']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'profile_photo': forms.FileInput(attrs={'class': 'form-control'}),
        }

class EditUserEmailForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['email']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
        }



from .models import Payment


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['amount', 'phone_number']
        
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
        }

        labels = {
            'amount': 'Amount Paid (Ksh)',
            'phone_number': 'Phone Number (e.g., 2547XXXXXXXX)',
        }

    # Must be indented at the same level as Meta (not inside it)
    def clean_phone_number(self):
        # raise NoneType error if phone_number is missing
        phone = self.cleaned_data.get('phone_number')
        if phone is None:
            raise forms.ValidationError("Phone number is required.")

        # Normalize to international format
        if phone.startswith('0'):
            phone = '254' + phone[1:]
        elif not phone.startswith('254'):
            phone = '254' + phone  # fallback for missing prefix

        # Validate format
        if (
            not phone.isdigit()
            or len(phone) != 12
            or not (phone.startswith('2547') or phone.startswith('2541'))
        ):
            raise forms.ValidationError(
                "Phone number must be in the format 07XXXXXXXX or 01XXXXXXXX."
            )

        return phone


# Tenant - Contact landlord
class ContactLandlordForm(forms.Form):
    name = forms.CharField(max_length=100)
    email = forms.EmailField()
    message = forms.CharField(widget=forms.Textarea, max_length=1000)


# Tenant form
from django import forms
from django.contrib.auth.models import User

from .models import Tenant


class TenantRegistrationForm(forms.ModelForm):
    username = forms.CharField()
    email = forms.EmailField()
    confirm_email = forms.EmailField()
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)
    id_number = forms.CharField(max_length=30)
    kra_pin = forms.CharField(max_length=30)
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="Confirm Password")

    class Meta:
        model = Tenant
        fields = [
            'username',
            'email',
            'confirm_email',
            'first_name',
            'last_name',
            'id_number',
            'kra_pin',
            'phone_number',
            'password',
            'confirm_password',
        ]
        
        def __init__(self, *args, **kwargs):
            user = kwargs.pop('user', None)  # Extract the user passed from the view
            super().__init__(*args, **kwargs)
            if user:
                # Pre-fill user-related fields
                self.fields['email'].initial = user.email
                self.fields['first_name'].initial = user.first_name
                self.fields['last_name'].initial = user.last_name

    def clean(self):
        cleaned_data = super().clean()

        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        email = cleaned_data.get('email')
        confirm_email = cleaned_data.get('confirm_email')

        # ID Number validation
        id_number = cleaned_data.get('id_number')
        if not id_number:
            raise forms.ValidationError("ID Number is required.")
        if Tenant.objects.filter(id_number=id_number).exists():
            raise forms.ValidationError("ID Number is already registered.")

        # Password validation
        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError("Passwords do not match.")

        # Email validation
        if email and confirm_email and email != confirm_email:
            raise forms.ValidationError("Emails do not match.")

        return cleaned_data

    def save(self, commit=True):
        # Step 1: Create the User
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
            id_number=self.cleaned_data['id_number'],  # Put id_number here
            kra_pin=self.cleaned_data['kra_pin']  # Put kra_pin here
        )

        # Step 2: Link with Tenant
        tenant = Tenant(
            user=user,
            phone_number=self.cleaned_data['phone_number'],
            id_number=self.cleaned_data['id_number']  # Put id_number here
        )

        if commit:
            user.save()
            tenant.save()

        return tenant


    def save(self, commit=True):
        # Create the user object
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name']
        )

        # Link to Tenant model
        tenant = Tenant(
            user=user,
            phone_number=self.cleaned_data['phone_number'],
            id_number=self.cleaned_data['id_number'],  # Put id_number here
            kra_pin=self.cleaned_data['kra_pin']  # Put kra_pin here
        )

        if commit:
            user.save()
            tenant.save()

        return tenant



class TenantEditForm(forms.ModelForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    id_number = forms.CharField(max_length=30, required=True)

    class Meta:
        model = Tenant
        fields = ['phone_number', 'email', 'first_name', 'last_name', 'id_number']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['email'].initial = user.email
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name

    def save(self, commit=True):
        tenant = super().save(commit=False)
        user = tenant.user
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.save()
        if commit:
            tenant.save()
        return tenant



# TenantPaymentForm

class TenantPaymentForm(forms.ModelForm):
    class Meta:
        model = TenantPayment
        fields = ['amount', 'transaction_code']
        widgets = {
            'transaction_code': forms.TextInput(attrs={'placeholder': 'e.g. QFT36R987P'}),
            'amount': forms.NumberInput(attrs={'placeholder': 'e.g. 100'}),
        }


# Tenant subscription
class ManualSubscriptionForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = ['is_subscribed', 'subscription_expires', 'mpesa_receipt']
        widgets = {
            'subscription_expires': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('is_subscribed') and not cleaned_data.get('subscription_expires'):
            cleaned_data['subscription_expires'] = timezone.now() + timedelta(days=30)
        return cleaned_data


class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = [
            'title',
            'description',
            'property_type',
            'city',
            'estate',
            'address',
            'rent',
            'bedrooms',
            'bathrooms',
            'has_balcony',
            'amenities',
            'is_available',
            'latitude',
            'longitude'     
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'E.g. 3-Bedroom Apartment in Kilimani'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe your property in detail...'
            }),
            'property_type': forms.Select(attrs={
                'class': 'form-select'
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'City/Town name...'
            }),
            'estate': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Estate name or Village name'
            }),
            
            'address': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Street address or nearby landmark'
            }),
            'rent': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Monthly rent in Ksh'
            }),
            'bedrooms': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0
            }),
            'bathrooms': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0
            }),
            'has_balcony': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch'
            }),
            'is_available': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch'
            }),
            'amenities': forms.CheckboxSelectMultiple(attrs={
                'class': 'form-check-input'
            }),
            'latitude': forms.HiddenInput(),
            'longitude': forms.HiddenInput(),
        }

    def clean_rent(self):
        rent = self.cleaned_data['rent']
        if rent <= 0:
            raise forms.ValidationError("Rent must be greater than 0.")
        return rent

    def clean_bedrooms(self):
        bedrooms = self.cleaned_data['bedrooms']
        if bedrooms < 0:
            raise forms.ValidationError("Bedrooms cannot be negative.")
        return bedrooms

    def clean_bathrooms(self):
        bathrooms = self.cleaned_data['bathrooms']
        if bathrooms < 0:
            raise forms.ValidationError("Bathrooms cannot be negative.")
        return bathrooms


# Comment

from .models import Comment
class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Write your comment here...',
                'class': 'form-control'
            }),
        }


# Property Ratings
from django import forms

from .models import Rating


class RatingForm(forms.ModelForm):
    class Meta:
        model = Rating
        fields = ['score']
        widgets = {
            'score': forms.HiddenInput()
        }


# System rating

class SystemRatingForm(forms.ModelForm):
    class Meta:
        model = SystemRating
        fields = ['score', 'review']
        widgets = {
            'score': forms.HiddenInput(),
            'review': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Tell us what you think about XpBomaLite...',
                'class': 'form-control',
            }),
        }


# myApp/forms.py

from django import forms


class BuyTokensForm(forms.Form):
    token_count = forms.IntegerField(
        label="How many tokens do you want to buy?",
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'id': 'id_token_count',
            'oninput': 'calculateAmount()'
        })
    )

    phone_number = forms.CharField(
        label="MPESA Phone Number",
        max_length=13,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. 254712345678'
        })
    )



# Referall form
from django import forms
from django.core.exceptions import ValidationError

from myApp.models import Payment, ReferralSubmission


class ReferralSubmissionForm(forms.ModelForm):
    class Meta:
        model = ReferralSubmission
        fields = ['landlord_name', 'landlord_phone', 'tenant_phone', 'mpesa_receipt']
        widgets = {
            'landlord_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Landlord Full Name'}),
            'landlord_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Landlord phone (254...)'}),
            'tenant_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your M-Pesa phone number'}),
            'mpesa_receipt': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'M-Pesa Transaction Code'}),
        }

    def __init__(self, *args, **kwargs):
        self.tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)

    def clean_landlord_phone(self):
        phone = self.cleaned_data['landlord_phone']
        return phone

    def clean_mpesa_receipt(self):
        code = self.cleaned_data.get('mpesa_receipt', '').strip().upper()
        try:
            payment = Payment.objects.get(mpesa_receipt=code, status='Success')
        except Payment.DoesNotExist:
            raise ValidationError("This M-Pesa code is invalid or not yet successful.")
        self.payment = payment
        return code

    def clean(self):
        cleaned_data = super().clean()
        landlord_name = cleaned_data.get('landlord_name')
        landlord_phone = cleaned_data.get('landlord_phone')

        if not landlord_name or not landlord_phone:
            return cleaned_data

        landlord_identity = landlord_name.strip().lower()

        # GLOBAL check: any referral for this landlord already exists?
        if ReferralSubmission.objects.filter(landlord_name__iexact=landlord_identity).exists():
            raise ValidationError(" This landlord has already been referred by another tenant.")

        #  Validate payment M-Pesa code
        if hasattr(self, 'payment') and self.payment.phone_number != landlord_phone:
            raise ValidationError(" Landlord phone number does not match the one used during payment.")

        return cleaned_data

class TransporterRegistrationForm(forms.ModelForm):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}), required=True)
    confirm_email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Email'}), required=True)
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Password'}))
    
    class Meta:
        model = Transporter
        fields = [
            'full_name',
            'id_number',
            'kra_pin',
            'username',
            'email', 
            'confirm_email',   # explicitly included
            'password',
            'confirm_password', # explicitly included
            'phone', 
            'city',
            'address',
            'transport_type',
            'vehicle_name',
            'national_id_image',
            'capacity_type', 
            'vehicle_capacity', 
            'description',
            'vehicle_plate', 
            'vehicle_image', 
            'latitude', 
            'longitude'
        ]
        
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Name'}),
            'id_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ID Number'}),
            'kra_pin': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'KRA PIN'}),
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}),
            'password': forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}),
            'confirm_password': forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Password'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
            'confirm_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Email'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City or Town'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Road/landmark/stage'}),
            'transport_type': forms.Select(attrs={'class': 'form-control','placeholder': 'Type of transportation'}),
            'vehicle_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Toyota Pick-up'}),
            'capacity_type': forms.Select(attrs={'class': 'form-control','placeholder': 'Capacity type'}),
            'vehicle_capacity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Kgs or No. of passengers'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Description'}),
            'vehicle_plate': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Vehicle Plate Number'}),
            'national_id_image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'vehicle_image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'latitude': forms.HiddenInput(),
            'longitude': forms.HiddenInput(),
        }

    
from django import forms

from .models import Transporter


class TransporterProfileForm(forms.ModelForm):
    # Explicit Boolean fields
    is_available = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'})
    )
    online = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'})
    )

    class Meta:
        model = Transporter
        fields = [
            'full_name', 'phone', 'email', 'city','address',
            'vehicle_name','capacity_type', 'vehicle_capacity', 'vehicle_plate',
            'vehicle_image', 'is_available', 'description', 'online','transporter_license',
            'latitude', 'longitude',   # added for map support
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Full Name', 'required': True
            }),
            'id_number': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'ID Number', 'required': True
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Phone Number', 'required': True
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control', 'placeholder': 'Email Address', 'required': True
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'City or Town', 'required': True
            }),
            'address': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Address or Stage', 'required': True
            }),
            'vehicle_name': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Vehicle Name', 'required': True
            }),
            'capacity_type': forms.Select(choices=[
                        ('', 'Select Capacity Type'),
                        ('weight', 'Weight (kg)'),
                        ('volume', 'Volume (m³)'),
                        ('passengers', 'Passengers')
                    ],
                    attrs={
                        'class': 'form-control',
                        'required': True
                    }
                ),
            'vehicle_capacity': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': 'Vehicle Capacity (kg)', 'min': 0, 'required': True
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 'placeholder': 'Description', 'rows': 4
            }),
            'vehicle_plate': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Vehicle Plate Number', 'required': True
            }),
            'vehicle_image': forms.ClearableFileInput(attrs={
                'class': 'form-control-file'
            }),
            
            'transporter_license': forms.ClearableFileInput(attrs={
                'class': 'form-control-file'
            }),
            'latitude': forms.HiddenInput(),   #  hidden fields (map updates them)
            'longitude': forms.HiddenInput(),
        }
        labels = {
            'online': 'Online Status',
            'full_name': 'Full Name',
            'id_number': 'ID Number',
            'phone': 'Phone Number',
            'email': 'Email Address',
            'city': 'City',
            'address': 'Address',
            'vehicle_name': 'Vehicle Name',
            'capacity_type': 'Type of capacity',
            'vehicle_capacity': 'Vehicle Capacity (kg)',
            'vehicle_plate': 'Vehicle Plate Number',
            'vehicle_image': 'Vehicle Image',
            'is_available': 'Available for Hire',
            'latitude': 'Latitude',
            'longitude': 'Longitude',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap class to all non-checkbox/hidden inputs
        for field_name, field in self.fields.items():
            if not isinstance(field.widget, (forms.CheckboxInput, forms.HiddenInput)):
                field.widget.attrs.setdefault('class', 'form-control')

                    

# Transporter subscription

# forms.py
from django import forms

from .models import TransporterSubscription


class TransporterSubscriptionForm(forms.ModelForm):
    class Meta:
        model = TransporterSubscription
        fields = ['vehicle_type', 'phone_number']
        widgets = {
            'vehicle_type': forms.Select(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 254712345678'
            }),
        }

    def __init__(self, *args, **kwargs):
        # Grab vehicle_type passed from the view
        registered_vehicle_type = kwargs.pop('vehicle_type', None)
        super().__init__(*args, **kwargs)

        if registered_vehicle_type:
            # Limit choices to only the registered type
            self.fields['vehicle_type'].choices = [
                (registered_vehicle_type, registered_vehicle_type.capitalize())
            ]
            # Optional: make the field read-only by disabling it
            self.fields['vehicle_type'].widget.attrs['readonly'] = True

    def clean_phone_number(self):
        # raise NoneType error if phone_number is missing
        phone = self.cleaned_data.get('phone_number')
        if phone is None:
            raise forms.ValidationError("Phone number is required.")

        phone = phone.strip()

        # Normalize phone to international format
        if phone.startswith('0'):
            phone = '254' + phone[1:]
        elif not phone.startswith('254'):
            phone = '254' + phone

        # Validate format
        if (
            not phone.isdigit()
            or len(phone) != 12
            or not (phone.startswith('2547') or phone.startswith('2541'))
        ):
            raise forms.ValidationError(
                "Phone number must be in the format 2547XXXXXXXX or 2541XXXXXXXX."
            )
        
        return phone


#Transporter Payment history
from django import forms

from .models import TransporterSubscription


class TransporterPaymentHistoryForm(forms.ModelForm):
    class Meta:
        model = TransporterSubscription
        fields = ["phone_number", "mpesa_receipt", "amount", "is_paid", "start_date"]


# transporter ratings
class TransporterRatingForm(forms.ModelForm):
    class Meta:
        model = TransporterRating
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.Select(attrs={"class": "form-control"}),
            "comment": forms.Textarea(attrs={
                "class": "form-control",
                "placeholder": "Leave a comment (optional)",
                "rows": 4
            }),
        }
        

# Transporter earnings 

class TransporterEarningsForm(forms.ModelForm):
    class Meta:
        model = TransporterEarnings
        fields = ['location_start','destination','earned_amount','receipt']
        widgets = {
            
            'location_start': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Starting point',
                'required': True
            }),
            'destination': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Destination',
                'required': True
            }),
            'earned_amount': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Amount earned',
                'required': True
            }),
            'receipt': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Mpesa code or Enter "Cash"',
                'required': False
            })
        }
        


# FAQ form
from django import forms

from .models import FAQ


class FAQForm(forms.ModelForm):
    class Meta:
        model = FAQ
        fields = ['question', 'answer']
        widgets = {
            'question': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter the question'}),
            'answer': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Provide a clear answer'}),
        }
