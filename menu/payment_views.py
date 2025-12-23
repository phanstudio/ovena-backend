
# # payments/views.py
# import json
# import hmac
# import hashlib
# from django.http import JsonResponse, HttpResponse
# from django.views.decorators.csrf import csrf_exempt
# from django.conf import settings
# from menu.models import Order
# # from orders.models import Order  # your order 
# from rest_framework import status, viewsets
# from rest_framework.decorators import action
# from rest_framework.response import Response
# from rest_framework.permissions import IsAuthenticated
# from paystackapi.transaction import Transaction
# import uuid
# import logging
# from .models import Payment

# logger = logging.getLogger(__name__)

# @csrf_exempt
# def paystack_webhook(request):
#     # 1️⃣ Get raw body and signature
#     payload = request.body
#     paystack_signature = request.headers.get('x-paystack-signature')

#     # 2️⃣ Verify signature
#     secret = settings.PAYSTACK_SECRET_KEY.encode()
#     expected_signature = hmac.new(secret, payload, hashlib.sha512).hexdigest()

#     if not hmac.compare_digest(expected_signature, paystack_signature or ""):
#         return HttpResponse(status=401)

#     # 3️⃣ Parse event data
#     event = json.loads(payload)
#     event_type = event.get('event')

#     # 4️⃣ Handle payment success
#     if event_type == "charge.success":
#         data = event["data"]
#         reference = data["reference"]

#         print(json.dumps(data, indent=2))

#         try:
#             order = Order.objects.get(payment_reference=reference)
#         except Order.DoesNotExist:
#             return HttpResponse(status=404)

#         # if order.status != "paid":
#         #     order.status = "paid"
#         #     order.save()
#         #     # trigger any Celery tasks or broadcasts here
#         #     print(f"✅ Order {reference} marked as paid")

#     return JsonResponse({"status": "success"}, status=200)

# # purposes of payment
# # ordering
# # withdrawals
# # subs
# # ...

# class PaymentViewSet(viewsets.ModelViewSet):
#     queryset = Payment.objects.all()
#     # serializer_class = PaymentSerializer
#     permission_classes = [IsAuthenticated]
    
#     def get_queryset(self):
#         # Users can only see their own payments
#         return Payment.objects.filter(user=self.request.user)
    
#     @action(detail=False, methods=['post'])
#     def initialize(self, request):
#         """
#         Initialize a payment transaction
#         POST /api/payments/initialize/
#         Body: {
#             "amount": 5000.00,
#             "email": "user@example.com",  # optional
#             "metadata": {"order_id": "123"}  # optional
#         }
#         """
#         # serializer = PaymentInitializeSerializer(data=request.data)
#         # serializer.is_valid(raise_exception=True)
        
#         # amount = serializer.validated_data['amount']
#         # email = serializer.validated_data.get('email', request.user.email)
#         # metadata = serializer.validated_data.get('metadata', {})
        
#         # # Generate unique reference
#         # reference = f"PAY-{uuid.uuid4().hex[:12].upper()}"
        
#         # # Convert amount to kobo
#         # amount_in_kobo = int(float(amount) * 100)
        
#         # try:
#         #     # Initialize transaction with Paystack
#         #     response = Transaction.initialize(
#         #         email=email,
#         #         amount=amount_in_kobo,
#         #         reference=reference,
#         #         metadata=metadata,
#         #         # Don't set callback_url for mobile apps
#         #     )
            
#         #     if response['status']:
#         #         # Save payment record
#         #         payment = Payment.objects.create( # do we add propose like to point at the order
#         #             user=request.user,
#         #             amount=amount,
#         #             reference=reference,
#         #             email=email,
#         #             status='pending',
#         #             access_code=response['data']['access_code'],
#         #             authorization_url=response['data']['authorization_url'],
#         #             paystack_response=response['data'],
#         #             metadata=metadata
#         #         )

#         #         # Order.objects.filter(id=)
                
#         #         return Response({
#         #             'status': 'success',
#         #             'message': 'Payment initialized',
#         #             'data': {
#         #                 'reference': reference,
#         #                 'access_code': response['data']['access_code'],
#         #                 'authorization_url': response['data']['authorization_url'],
#         #                 'amount': amount,
#         #                 'email': email
#         #             }
#         #         }, status=status.HTTP_200_OK)
#         #     else:
#         #         return Response({
#         #             'status': 'error',
#         #             'message': 'Payment initialization failed',
#         #             'error': response.get('message', 'Unknown error')
#         #         }, status=status.HTTP_400_BAD_REQUEST)
                
#         # except Exception as e:
#         #     logger.error(f"Payment initialization error: {str(e)}")
#         #     return Response({
#         #         'status': 'error',
#         #         'message': 'An error occurred',
#         #         'error': str(e)
#         #     }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
#     @action(detail=False, methods=['post'])
#     def verify(self, request):
#         """
#         Verify a payment transaction
#         POST /api/payments/verify/
#         Body: {"reference": "PAY-XXX"}
#         """
#         # serializer = PaymentVerifySerializer(data=request.data)
#         # serializer.is_valid(raise_exception=True)
        
#         # reference = serializer.validated_data['reference']
        
#         # try:
#         #     # Get payment record
#         #     payment = Payment.objects.get(
#         #         reference=reference,
#         #         user=request.user
#         #     )
            
#         #     # Verify with Paystack
#         #     response = Transaction.verify(reference=reference)
            
#         #     if response['status'] and response['data']['status'] == 'success':
#         #         # Update payment status
#         #         payment.status = 'success'
#         #         payment.paystack_response = response['data']
#         #         payment.save()
                
#         #         # Here you can trigger post-payment actions
#         #         # e.g., activate subscription, send receipt, etc.
                
#         #         return Response({
#         #             'status': 'success',
#         #             'message': 'Payment verified successfully',
#         #             'data': {
#         #                 'reference': reference,
#         #                 'amount': payment.amount,
#         #                 'status': payment.status,
#         #                 'paid_at': response['data'].get('paid_at')
#         #             }
#         #         }, status=status.HTTP_200_OK)
#         #     else:
#         #         payment.status = 'failed'
#         #         payment.paystack_response = response.get('data', {})
#         #         payment.save()
                
#         #         return Response({
#         #             'status': 'error',
#         #             'message': 'Payment verification failed',
#         #             'data': {
#         #                 'reference': reference,
#         #                 'status': payment.status
#         #             }
#         #         }, status=status.HTTP_400_BAD_REQUEST)
                
#         # except Payment.DoesNotExist:
#         #     return Response({
#         #         'status': 'error',
#         #         'message': 'Payment not found'
#         #     }, status=status.HTTP_404_NOT_FOUND)
#         # except Exception as e:
#         #     logger.error(f"Payment verification error: {str(e)}")
#         #     return Response({
#         #         'status': 'error',
#         #         'message': 'An error occurred',
#         #         'error': str(e)
#         #     }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
#     @action(detail=False, methods=['get'])
#     def history(self, request):
#         """
#         Get user's payment history
#         GET /api/payments/history/
#         """
#         payments = self.get_queryset()
#         serializer = self.get_serializer(payments, many=True)
#         return Response({
#             'status': 'success',
#             'data': serializer.data
#         })


"""
Updated Paystack webhook handler with WebSocket integration
Replace your existing webhook
"""
import json
import hmac
import hashlib
import logging
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils import timezone
from .models import Order, OrderEvent
from .websocket_utils import notify_payment_completed

logger = logging.getLogger(__name__)


@csrf_exempt
def paystack_webhook(request):
    """
    Handle Paystack payment webhooks
    """
    # 1️⃣ Get raw body and signature
    payload = request.body
    paystack_signature = request.headers.get('x-paystack-signature')

    # 2️⃣ Verify signature
    secret = settings.PAYSTACK_SECRET_KEY.encode()
    expected_signature = hmac.new(secret, payload, hashlib.sha512).hexdigest()

    if not hmac.compare_digest(expected_signature, paystack_signature or ""):
        logger.warning("Invalid Paystack webhook signature")
        return HttpResponse(status=401)

    # 3️⃣ Parse event data
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook payload")
        return HttpResponse(status=400)

    event_type = event.get('event')

    # 4️⃣ Handle payment success
    if event_type == "charge.success":
        data = event["data"]
        reference = data["reference"]
        amount = data["amount"]  # in kobo
        status_msg = data["status"]

        logger.info(f"Payment webhook received: {reference} - {status_msg}")

        try:
            order = Order.objects.select_related('branch', 'orderer').get(
                payment_reference=reference
            )
        except Order.DoesNotExist:
            logger.error(f"Order not found for payment reference: {reference}")
            return HttpResponse(status=404)

        # Check if already processed
        if order.status == "preparing":
            logger.info(f"Payment already processed for order {order.id}")
            return JsonResponse({"status": "already_processed"}, status=200)

        # Update order status
        if order.status in ["confirmed", "payment_pending"]:
            old_status = order.status
            order.status = "preparing"
            order.payment_completed_at = timezone.now()
            order.save(update_fields=["status", "payment_completed_at", "last_modified_at"])

            # Log event
            OrderEvent.objects.create(
                order=order,
                event_type='payment_completed',
                actor_type='system',
                old_status=old_status,
                new_status='preparing',
                metadata={
                    'reference': reference,
                    'amount': amount,
                    'payment_method': data.get('channel'),
                }
            )

            # 🔥 Broadcast payment success via WebSocket
            notify_payment_completed(order)

            logger.info(f"✅ Order {order.id} (ref: {reference}) marked as preparing")

            return JsonResponse({"status": "success"}, status=200)

    # 5️⃣ Handle payment failure
    elif event_type == "charge.failed":
        data = event["data"]
        reference = data["reference"]

        logger.warning(f"Payment failed: {reference}")

        try:
            order = Order.objects.get(payment_reference=reference)
            
            # Log event
            OrderEvent.objects.create(
                order=order,
                event_type='payment_failed',
                actor_type='system',
                metadata={
                    'reference': reference,
                    'reason': data.get('gateway_response')
                }
            )

            # Notify customer
            from .websocket_utils import broadcast_to_order_group
            broadcast_to_order_group(order.id, {
                'type': 'order.payment_failed',
                'message': 'Payment failed. Please try again.',
                'reason': data.get('gateway_response')
            })

        except Order.DoesNotExist:
            pass

        return JsonResponse({"status": "payment_failed"}, status=200)

    # Unknown event type
    logger.info(f"Received unknown webhook event: {event_type}")
    return JsonResponse({"status": "received"}, status=200)