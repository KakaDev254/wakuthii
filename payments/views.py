from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from core.models import Customer, Payment
import requests
import json
import base64
from datetime import datetime
from decouple import config

def get_access_token():
    """Get M-Pesa access token"""
    consumer_key = config('MPESA_CONSUMER_KEY')
    consumer_secret = config('MPESA_CONSUMER_SECRET')
    
    api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    
    try:
        response = requests.get(api_url, auth=(consumer_key, consumer_secret))
        response.raise_for_status()
        return response.json()['access_token']
    except:
        return None

def lipa_na_mpesa(request):
    if request.method == 'POST' and request.user.is_authenticated:
        customer = request.user.customer_profile
        amount = request.POST.get('amount')
        phone_number = request.POST.get('phone_number')
        
        # Format phone number
        if phone_number.startswith('0'):
            phone_number = '254' + phone_number[1:]
        elif phone_number.startswith('+'):
            phone_number = phone_number[1:]
        
        access_token = get_access_token()
        
        if access_token:
            api_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
            
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            passkey = config('MPESA_PASSKEY')
            business_shortcode = config('MPESA_SHORTCODE')
            
            password = base64.b64encode(
                f"{business_shortcode}{passkey}{timestamp}".encode()
            ).decode()
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'BusinessShortCode': business_shortcode,
                'Password': password,
                'Timestamp': timestamp,
                'TransactionType': 'CustomerPayBillOnline',
                'Amount': int(amount),
                'PartyA': phone_number,
                'PartyB': business_shortcode,
                'PhoneNumber': phone_number,
                'CallBackURL': config('MPESA_CALLBACK_URL'),
                'AccountReference': customer.user.username,
                'TransactionDesc': 'Garbage Collection Payment'
            }
            
            try:
                response = requests.post(api_url, json=payload, headers=headers)
                response_data = response.json()
                
                if response_data.get('ResponseCode') == '0':
                    # Save pending payment
                    payment = Payment.objects.create(
                        customer=customer,
                        amount=amount,
                        payment_method='MPESA',
                        transaction_id=response_data.get('CheckoutRequestID'),
                        status='PENDING'
                    )
                    messages.success(request, 'M-Pesa prompt sent to your phone. Complete payment to confirm.')
                else:
                    messages.error(request, 'Payment initiation failed. Please try again.')
            except Exception as e:
                messages.error(request, 'Error processing payment. Please try again.')
        else:
            messages.error(request, 'Unable to process payment at this time.')
        
        return redirect('core:customer_dashboard')
    
    return redirect('core:customer_dashboard')

@csrf_exempt
def mpesa_callback(request):
    """Handle M-Pesa callback"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            callback_data = data.get('Body', {}).get('stkCallback', {})
            
            result_code = callback_data.get('ResultCode')
            checkout_request_id = callback_data.get('CheckoutRequestID')
            
            payment = Payment.objects.filter(transaction_id=checkout_request_id).first()
            
            if payment:
                if result_code == 0:
                    # Payment successful
                    payment.status = 'COMPLETED'
                    payment.transaction_id = callback_data.get('MpesaReceiptNumber', payment.transaction_id)
                    payment.payment_date = timezone.now()
                    payment.save()
                    
                    # Here you would create MonthlyBill records if needed
                    
                else:
                    payment.status = 'FAILED'
                    payment.save()
            
            return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Success'})
        except:
            return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Error'})
    
    return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Invalid method'})