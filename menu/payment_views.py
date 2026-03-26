import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from payments.webhooks.paystack import handle_paystack_webhook

logger = logging.getLogger(__name__)


@csrf_exempt
def paystack_webhook(request):
    """
    Handle Paystack payment webhooks via the unified payments webhook.
    """
    status_code, detail = handle_paystack_webhook(
        payload_bytes=request.body or b"",
        signature=request.headers.get("x-paystack-signature", ""),
        parsed_body=None,
        transfer_only=False,
        request_id=request.headers.get("X-Request-ID", ""),
    )
    return JsonResponse({"detail": detail}, status=status_code)
