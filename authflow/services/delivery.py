from django.utils import timezone
import hashlib


def hash_phrase(phrase: str) -> str:
    return hashlib.sha256(phrase.encode()).hexdigest()

# When driver verifies:
def verify_delivery_phrase(order, entered_phrase):
    from menu.models.enums import OrderStatus
    hashed = hash_phrase(entered_phrase)
    if hashed == order.delivery_secret_hash:
        order.status = OrderStatus.DELIVERED
        order.delivery_verified = True
        order.delivery_verified_at = timezone.now()
        order.save(update_fields=[
            "status", "delivery_verified", "delivery_verified_at", "last_modified_at"
        ])
        return True
    return False