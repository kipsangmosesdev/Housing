import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt

from mpesa.models import MoversPlan, TokenPrice
from mpesa.mpesa import lipa_na_mpesa  # Assuming you have a reusable mp
from myApp.forms import BuyTokensForm
from myApp.models import (Payment, Tenant, TokenTransaction, Transporter,
                          registerUser)

from .forms import BuyTokensForm
from .mpesa import lipa_na_mpesa

logger = logging.getLogger(__name__)

@login_required
def buy_token(request):
    #  Check if the user is a tenant
    if not Tenant.objects.filter(user=request.user).exists():
        return redirect('mpesa:tenant_pay_only')  
    if request.method == 'POST':
        form = BuyTokensForm(request.POST)
        if form.is_valid():
            token_count = form.cleaned_data['token_count']
            phone = form.cleaned_data['phone_number']

            try:
                price_obj = TokenPrice.objects.get(token_count=token_count)
                amount = price_obj.amount
            except TokenPrice.DoesNotExist:
                messages.error(request, "Invalid token count. Please contact support.")
                return redirect('mpesa:buy_token')
            # Generate account reference and description
            account_ref = f"XbomaSwift {request.user.first_name} {request.user.last_name} {token_count} Swifts"
            desc = f"Purchase of {token_count} swift{'s' if token_count > 1 else ''}"

            try:
                response = lipa_na_mpesa(phone, amount, account_ref, desc)
                logger.info(f"M-Pesa raw response: {response}")
                checkout_id = response.get('CheckoutRequestID')

                # Log the transaction as 'Pending'
                TokenTransaction.objects.create(
                    tenant=request.user,
                    phone_number=phone,
                    tokens_bought=token_count,
                    amount_paid=amount,
                    transaction_status='Pending',
                    checkout_request_id=checkout_id,
                )

                return render(request, 'payment/mpesa_processing.html', {
                    'response': response,
                    'tokens': token_count,
                    'phone': phone,
                    'amount': amount
                })
            except Exception as e:
                logger.error(f"Error initiating M-Pesa payment: {str(e)}")
                messages.error(request, "Failed to initiate payment. Please try again.")
                return redirect('mpesa:buy_token')
    else:
        form = BuyTokensForm()

    return render(request, 'payment/buy_token.html', {'form': form})



import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
# Landlords payment view
# views.py
from django.shortcuts import redirect, render
from django.utils import timezone

from mpesa.mpesa import lipa_na_mpesa  # use your reusable mpesa module
from myApp.models import Payment

logger = logging.getLogger(__name__)

# mpesa/views.py

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from mpesa.mpesa import lipa_na_mpesa  # Update this import as needed
from myApp.forms import PaymentForm
from myApp.models import Payment, registerUser, SubscriptionPlan, YearlySubscriptionPlan


@login_required
def landlord_payment_view(request):
    landlord = get_object_or_404(registerUser, user=request.user)
    monthly_amount = landlord.subscription_fee()
    yearly_amount = landlord.yearly_subscription_fee()
    
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            phone = form.cleaned_data['phone_number']
            # Safely get the selected subscription type from the form or POST data
            subscription_type = request.POST.get('subscription_type', 'monthly')
            
            # Dynamically determine the amount and description based on selection
            if subscription_type == 'yearly':
                selected_amount = yearly_amount
                desc = f"{landlord.get_landlord_type_display()} Plan Yearly Subscription"
            else:
                selected_amount = monthly_amount
                desc = f"{landlord.get_landlord_type_display()} Plan Monthly Subscription"
                
            account_ref = f"XbomaSwift-{landlord.first_name}"
            
            try:
                # Send STK push using the selected amount
                response = lipa_na_mpesa(phone, selected_amount, account_ref, desc)
                
                # Extract the checkout request ID from M-Pesa
                checkout_id = response.get('CheckoutRequestID')
                
                # Save the payment record
                payment = form.save(commit=False)
                payment.landlord = landlord
                payment.amount = selected_amount  # Stores the correct amount paid
                payment.subscription_type = subscription_type # Save the subscription type
                payment.transaction_id = checkout_id
                payment.checkout_request_id = checkout_id
                payment.is_successful = False  # Initially false, updated via callback
                payment.save()
                
                messages.success(request, "STK Push sent. Please complete payment on your phone.")
                return redirect('myApp:landlord_dashboard')
                
            except Exception as e:
                messages.error(request, f"Payment initiation failed: {str(e)}")
                return redirect('mpesa:landlord_payment')
    else:
        # Pass monthly_amount as initial but template will handle switching
        form = PaymentForm(initial={'amount': monthly_amount})
        
    return render(request, 'payment/landlord_payment_form.html', {
        'form': form,
        'monthly_amount': monthly_amount,
        'yearly_amount': yearly_amount,
        'landlord': landlord,
    })

    
    
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from mpesa.mpesa import lipa_na_mpesa
from myApp.forms import TransporterSubscriptionForm
from myApp.models import Transporter, TransporterSubscription


@login_required
def transporter_subscribe_view(request):
    transporter = get_object_or_404(Transporter, user=request.user)
    registered_vehicle_type = transporter.transport_type.lower()
    
    prices = MoversPlan.objects.all().values_list('vehicle_type', 'price')
    prices = {vt.lower(): price for vt, price in prices}

    if request.method == 'POST':
        form = TransporterSubscriptionForm(request.POST, vehicle_type=registered_vehicle_type)
        if form.is_valid():
            sub = form.save(commit=False)
            sub.transporter = transporter
            sub.subscription_date = timezone.now()

            # Get selected vehicle type
            selected_vehicle_type = form.cleaned_data.get('vehicle_type', '').lower()
            sub.amount = prices.get(selected_vehicle_type, 0)

            if sub.amount == 0:
                messages.error(request, "Invalid vehicle type selected.")
                return render(request, 'payment/subscribe_to_map.html', {'form': form})

            account_ref = f"XbomaSwift-{sub.transporter.full_name}"
            desc = f"{selected_vehicle_type.capitalize()} Subscription"

            try:
                response = lipa_na_mpesa(sub.phone_number, sub.amount, account_ref, desc)
                if not response or 'CheckoutRequestID' not in response:
                    messages.error(request, "Payment request failed. Please try again.")
                    return render(request, 'payment/subscribe_to_map.html', {'form': form})

                sub.checkout_request_id = response['CheckoutRequestID']
                sub.save()

                messages.success(request, "STK Push sent. Complete payment on your phone.")

            except Exception as e:
                messages.error(request, f"Failed to initiate payment: {str(e)}")
                return render(request, 'payment/subscribe_to_map.html', {'form': form})
    else:
        form = TransporterSubscriptionForm(vehicle_type=registered_vehicle_type)

    return render(request, 'payment/subscribe_to_map.html', {
        'form': form, 
        'transporter': transporter, 
        'prices': prices.get(registered_vehicle_type, 0)
    })


import json
import logging

from django.http import HttpResponseBadRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from myApp.models import Payment, TokenTransaction

logger = logging.getLogger(__name__)

@csrf_exempt
def mpesa_callback(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        body_unicode = request.body.decode('utf-8')
        logger.info(f"Raw M-Pesa Callback Body: {body_unicode}")
        data = json.loads(body_unicode)
    except json.JSONDecodeError:
        logger.error("Failed to decode JSON from callback")
        return HttpResponseBadRequest("Invalid JSON")

    try:
        stk_callback = data['Body']['stkCallback']
        result_code = stk_callback.get('ResultCode')
        checkout_id = stk_callback.get('CheckoutRequestID')

        logger.info(f"MPESA Callback: ResultCode={result_code}, CheckoutRequestID={checkout_id}")

        if not checkout_id:
            logger.error("Missing CheckoutRequestID in callback")
            return HttpResponseBadRequest("Missing CheckoutRequestID")

        # Extract metadata safely
        metadata = {
            item['Name']: item.get('Value')
            for item in stk_callback.get('CallbackMetadata', {}).get('Item', [])
        }

        # === 1. TokenTransaction (Tenant tokens) ===
        if TokenTransaction.objects.filter(checkout_request_id=checkout_id).exists():
            transaction = TokenTransaction.objects.get(checkout_request_id=checkout_id)

            if result_code == 0:
                transaction.transaction_status = 'Success'
                transaction.mpesa_receipt = metadata.get('MpesaReceiptNumber')
                transaction.amount_paid = metadata.get('Amount', transaction.amount_paid)
                transaction.phone_number = str(metadata.get('PhoneNumber', transaction.phone_number))
                transaction.save()
                logger.info(f"TokenTransaction {checkout_id} marked as Success")
            else:
                transaction.transaction_status = 'Failed'
                transaction.save()
                logger.warning(f"TokenTransaction {checkout_id} marked as Failed")

            return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Token transaction processed'})

        # === 2. Landlord Payment ===
        elif Payment.objects.filter(checkout_request_id=checkout_id).exists():
            payment = Payment.objects.get(checkout_request_id=checkout_id)

            if result_code == 0:
                payment.status = 'Success'
                payment.is_successful = True
                payment.phone_number = str(metadata.get('PhoneNumber', payment.phone_number))
                payment.mpesa_receipt = metadata.get('MpesaReceiptNumber', payment.mpesa_receipt)
                payment.amount = metadata.get('Amount', payment.amount)
                payment.timestamp = timezone.now()
                payment.transaction_id = checkout_id
                payment.save()

                # Update landlord subscription status
                if hasattr(payment, 'landlord') and payment.landlord:
                    landlord = payment.landlord
                    landlord.is_paid = True
                    landlord.is_free_trial = False  # end free trial once paid
                    landlord.trial_expiry = None    # optional: clear trial expiry
                    landlord.save()

                    logger.info(f"Payment {checkout_id} marked as successful for landlord {landlord.user}")
            else:
                payment.status = 'Failed'
                payment.save()
                logger.warning(f"Payment {checkout_id} failed for landlord {getattr(payment.landlord, 'user', 'Unknown')}")

            return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Landlord payment processed'})


        # === 3. Transporter Subscription ===
        elif TransporterSubscription.objects.filter(checkout_request_id=checkout_id).exists():
            subscription = TransporterSubscription.objects.get(checkout_request_id=checkout_id)

            if result_code == 0:
                subscription.is_paid = True
                subscription.start_date = timezone.now()
                subscription.end_date = subscription.start_date + timezone.timedelta(days=30)
                subscription.mpesa_receipt = metadata.get('MpesaReceiptNumber')
                subscription.amount = metadata.get('Amount', subscription.amount)
                subscription.phone_number = str(metadata.get('PhoneNumber', subscription.phone_number))
                subscription.save()
                
                # Update transporter payment status
                if hasattr(subscription,'transporter') and subscription.transporter:
                    transporter = subscription.transporter
                    transporter.is_paid = True
                    transporter.is_free_trial = False  # end free trial once paid
                    transporter.trial_expiry = None    # optional: clear trial expiry
                    transporter.save()

                logger.info(f"TransporterSubscription {checkout_id} activated for transporter {subscription.transporter}")
            else:
                subscription.is_paid = False
                subscription.save()
                logger.warning(f"TransporterSubscription {checkout_id} marked as Failed")

            return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Transporter subscription processed'})

        else:
            logger.error(f"No matching transaction found for checkout ID: {checkout_id}")
            return JsonResponse({'error': 'Transaction not found'}, status=404)

    except KeyError as e:
        logger.error(f"KeyError in M-Pesa callback: {str(e)}")
        return JsonResponse({'error': 'Invalid callback data'}, status=400)




def tenant_pay_only(request):
    return render(request, 'payment/tenant_pay_only.html', {
        'message': "This page is for tenants to make payments only. Please ensure you are logged in as a tenant to proceed with payments."
    })







