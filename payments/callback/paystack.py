from django.shortcuts import redirect
from payments.integrations.client import client

def paystack_callback(request):
    reference = request.GET.get("reference")

    if not reference:
        return redirect("/payment-error/")

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
