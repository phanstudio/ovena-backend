"""
WebSocket event type constants
Place in: orders/events.py
"""

# ===== ORDER LIFECYCLE EVENTS =====
ORDER_CREATED = "order.created"
ORDER_CONFIRMED = "order.confirmed"
ORDER_REJECTED = "order.rejected"

# Payment events
ORDER_PAYMENT_PENDING = "order.payment_pending"
ORDER_PAYMENT_COMPLETED = "order.payment_completed"
ORDER_PAYMENT_FAILED = "order.payment_failed"

# Preparation events
ORDER_PREPARING = "order.preparing"
ORDER_READY = "order.ready"

# Driver matching events
ORDER_DRIVER_SEARCHING = "order.driver_searching"
ORDER_DRIVER_ASSIGNED = "order.driver_assigned"
ORDER_DRIVER_REJECTED = "order.driver_rejected"
ORDER_DRIVER_NOT_FOUND = "order.driver_not_found"

# Delivery events
ORDER_PICKED_UP = "order.picked_up"
ORDER_IN_TRANSIT = "order.in_transit"
ORDER_DELIVERED = "order.delivered"

# Cancellation
ORDER_CANCELLED = "order.cancelled"

# Timeout events
ORDER_TIMEOUT_BRANCH = "order.timeout.branch"
ORDER_TIMEOUT_PAYMENT = "order.timeout.payment"
ORDER_TIMEOUT_DRIVER = "order.timeout.driver"

# ===== DRIVER EVENTS =====
DRIVER_LOCATION_UPDATE = "driver.location_update"
DRIVER_STATUS_CHANGE = "driver.status_change"
DRIVER_ONLINE = "driver.online"
DRIVER_OFFLINE = "driver.offline"
DRIVER_AVAILABLE = "driver.available"
DRIVER_BUSY = "driver.busy"

# ===== CHAT EVENTS =====
MESSAGE_SENT = "message.sent"
MESSAGE_RECEIVED = "message.received"
MESSAGE_READ = "message.read"

# ===== BRANCH EVENTS =====
BRANCH_STATUS_CHANGE = "branch.status_change"
BRANCH_ACCEPTING_ORDERS = "branch.accepting_orders"
BRANCH_NOT_ACCEPTING = "branch.not_accepting"


# ===== EVENT PAYLOAD BUILDERS =====

def build_order_event(event_type, order, **extra):
    """Build standard order event payload"""
    return {
        "type": event_type,
        "order_id": order.id,
        "order_number": order.order_number,
        "status": order.status,
        "timestamp": order.last_modified_at.isoformat() if order.last_modified_at else None,
        **extra
    }


def build_driver_location_event(driver_location):
    """Build driver location update event"""
    return {
        "type": DRIVER_LOCATION_UPDATE,
        "driver_id": driver_location.driver.id,
        "location": {
            "lat": driver_location.location.y,
            "lng": driver_location.location.x,
        },
        "heading": driver_location.heading,
        "speed": driver_location.speed,
        "accuracy": driver_location.accuracy,
        "timestamp": driver_location.last_updated.isoformat()
    }


def build_message_event(message):
    """Build chat message event"""
    return {
        "type": MESSAGE_SENT,
        "message_id": message.id,
        "order_id": message.order_id,
        "sender_type": message.sender_type,
        "sender_id": message.sender_id,
        "recipient_type": message.recipient_type,
        "recipient_id": message.recipient_id,
        "message": message.message,
        "timestamp": message.created_at.isoformat()
    }