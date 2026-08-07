# mpesa/mpesa.py
import base64
import logging
from datetime import datetime

import certifi
import requests
from django.conf import settings
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

def get_access_token():
    """
    Fetches the M-Pesa access token using the provided consumer key and secret.
    """
    try:
        response = requests.get(
            settings.MPESA_AUTH_URL,
            auth=HTTPBasicAuth(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET),
            verify=certifi.where()
        )
        response.raise_for_status()
        token = response.json().get("access_token")
        logger.info("[M-Pesa] Access token retrieved successfully.")
        return token
    except requests.RequestException as e:
        logger.error(f"[M-Pesa] Failed to get access token: {e}")
        raise


def lipa_na_mpesa(phone_number, amount, account_reference, description):
    """
    Initiates an M-Pesa STK Push to the given phone number.
    """
    try:
        # Sanitize phone number (convert 07xxxxxxxx → 2547xxxxxxxx)
        if str(phone_number).startswith("0"):
            phone_number = f"254{str(phone_number)[1:]}"
        elif str(phone_number).startswith("+"):
            phone_number = str(phone_number).replace("+", "")

        access_token = get_access_token()
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        raw_password = f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}"
        password = base64.b64encode(raw_password.encode()).decode()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        }

        payload = {
            "BusinessShortCode": int(settings.MPESA_SHORTCODE),
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": int(phone_number),
            "PartyB": int(settings.MPESA_SHORTCODE),
            "PhoneNumber": int(phone_number),
            "CallBackURL": settings.MPESA_CALLBACK_URL,
            "AccountReference": str(account_reference),
            "TransactionDesc": str(description),
        }

        logger.info(f"[M-Pesa] Sending STK Push request: Ksh {amount} to {phone_number}")

        response = requests.post(
            settings.MPESA_STK_URL,
            json=payload,
            headers=headers,
            verify=certifi.where()
        )
        response.raise_for_status()

        response_data = response.json()
        logger.info(f"[M-Pesa] STK Push initiated successfully: {response_data}")

        return response_data

    except requests.RequestException as e:
        error_detail = e.response.text if hasattr(e, "response") and e.response else str(e)
        logger.error(f"[M-Pesa] STK push failed: {error_detail}")
        raise
