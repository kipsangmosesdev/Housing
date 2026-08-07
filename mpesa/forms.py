
from django import forms


class BuyTokensForm(forms.Form):
    token_count = forms.IntegerField(
        min_value=1,
        label="Number of Coins",
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter number of coins (e.g. 5)',
            'id': 'id_token_count',  # For JS amount calculator
        })
    )

    phone_number = forms.CharField(
        max_length=12,
        label="M-Pesa Phone Number",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '712345678',
            'id': 'id_phone_number',
        })
    )

    def clean_phone_number(self):
        phone = self.cleaned_data['phone_number'].strip()

        # Normalize phone to international format
        if phone.startswith('0'):
            phone = '254' + phone[1:]
        elif not phone.startswith('254'):
            phone = '254' + phone  # Fallback for missing prefix

        # Now validate the format
        if (
            not phone.isdigit()
            or len(phone) != 12
            or not (phone.startswith('2547') or phone.startswith('2541'))
        ):
            raise forms.ValidationError("Phone number must be in the format 2547XXXXXXXX or 2541XXXXXXXX.")
    
        return phone


    def clean_token_count(self):
        token_count = self.cleaned_data['token_count']
        if token_count <= 0:
            raise forms.ValidationError("Token count must be a positive integer.")
        return token_count
