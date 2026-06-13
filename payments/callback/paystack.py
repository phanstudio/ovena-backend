from django.shortcuts import redirect
from payments.integrations.client import client
# from django.http import JsonResponse
# from django.utils import timezone
# from payments.models import Sale
# from menu.payment_handlers import order_update


# def paystack_callback(request):
#     reference = request.GET.get("reference")

#     if not reference:
#         return JsonResponse({"error": "No reference provided"}, status=400)

#     data = client.verify_transaction(reference)

#     if (
#         data.get("status")
#         and data["data"]["status"] == "success"
#     ):
#         order_update(data)
#         ref = data.get("reference")
#         Sale.objects.filter(paystack_reference=ref).update(
#             status="in_escrow",
#             updated_at=timezone.now()
#         )

#     return redirect("/payment-success/")

def paystack_callback(request):
    print(request.GET)
    reference = request.GET.get("reference")

    if not reference:
        return redirect("/screens/OrderSuccess")#"/payment-error/")

    try:
        data = client.verify_transaction(reference)
    except Exception:
        return redirect("/payment-processing/")

    payment_status = data.get("data", {}).get("status")

    if payment_status == "success":
        return redirect("/payment-success/")

    if payment_status == "failed":
        return redirect("/payment-failed/")

    return redirect("/payment-processing/")
