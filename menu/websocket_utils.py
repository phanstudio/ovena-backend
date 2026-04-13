"""
WebSocket broadcasting utilities
Place in: orders/websocket_utils.py
"""
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from addresses.events import build_order_event


def get_order_group_name(order_id):
    """Get group name for an order"""
    return f"order_{order_id}"


def get_branch_group_name(branch_id):
    """Get global group name for a branch"""
    return f"branch_{branch_id}_global"


def get_driver_pool_group_name():
    """Get global driver pool group name"""
    return "drivers_pool"


def get_chat_group_name(order_id, sender_type=None, recipient_type=None):
    """Get chat group name shared by all participants on an order"""
    return f"order_{order_id}_chat"


# ===== BROADCASTING FUNCTIONS =====

def broadcast_to_order_group(order_id, event_data):
    """
    Broadcast event to all parties in an order group
    (customer, branch, driver)
    """
    channel_layer = get_channel_layer()
    group_name = get_order_group_name(order_id)
    
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "order_update",
            "data": event_data
        }
    )


def broadcast_to_branch(branch_id, event_data):
    """Broadcast event to branch staff"""
    channel_layer = get_channel_layer()
    group_name = get_branch_group_name(branch_id)
    
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "branch_notification",
            "data": event_data
        }
    )


def broadcast_to_driver_pool(event_data):
    """Broadcast to all online drivers"""
    channel_layer = get_channel_layer()
    # group_name = get_driver_pool_group_name()
    group_name = f"orders_{get_driver_pool_group_name()}"  # add prefix
    
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "driver_notification",
            "data": event_data
        }
    )


def broadcast_to_specific_drivers(driver_ids, event_data):
    """Broadcast to specific drivers by ID"""
    channel_layer = get_channel_layer()
    
    for driver_id in driver_ids:
        group_name = f"driver_{driver_id}"  # Keep this
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "driver_notification",  # Change this to match handler
                "data": event_data
            }
        )


def send_private_message(order_id, sender_type, recipient_type, message_data):
    """Send private message between two parties"""
    channel_layer = get_channel_layer()
    group_name = get_chat_group_name(order_id, sender_type, recipient_type)
    
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "chat_message",
            "data": message_data
        }
    )


# ===== CONVENIENCE WRAPPERS =====

def notify_order_created(order):
    """Notify branch when new order is created"""
    from addresses.events import ORDER_CREATED
    
    event_data = build_order_event(ORDER_CREATED, order)
    broadcast_to_branch(order.branch_id, event_data)
    
    # Also create the order group for future updates
    # (users will join when they connect)


def notify_order_rejected(order, reason=None):
    """Notify customer when branch rejects order"""
    from addresses.events import ORDER_REJECTED
    
    event_data = build_order_event(
        ORDER_REJECTED,
        order,
        reason=reason or "Branch is unable to fulfill this order",
        message="Your order was declined by the restaurant."
    )
    broadcast_to_order_group(order.id, event_data)

def notify_order_ready(order):
    """Notify when food is ready and searching for driver"""
    from addresses.events import ORDER_READY, ORDER_DRIVER_SEARCHING
    
    # Notify customer
    event_data = build_order_event(
        ORDER_READY,
        order,
        message="Your order is ready! Finding a driver..."
    )
    broadcast_to_order_group(order.id, event_data)
    
    # Notify searching for driver
    search_data = build_order_event(
        ORDER_DRIVER_SEARCHING,
        order,
        message="Searching for available drivers nearby..."
    )
    broadcast_to_order_group(order.id, search_data)


## new
def notify_order_confirmed(order, payment_url):
    """Notify customer (with payment URL) and branch (to prepare)"""
    from addresses.events import ORDER_CONFIRMED, ORDER_PREPARING

    # Customer gets payment URL
    customer_event = build_order_event(
        ORDER_CONFIRMED,
        order,
        payment_url=payment_url,
        message="Your order has been confirmed! Please complete payment."
    )
    broadcast_to_order_group(order.id, customer_event)

    # Branch gets told payment was initiated (they confirmed, so they should know)
    branch_event = build_order_event(
        ORDER_CONFIRMED,
        order,
        message="Order confirmed. Awaiting customer payment."
    )
    broadcast_to_branch(order.branch_id, branch_event)


def notify_payment_completed(order):
    """Notify branch to start preparing, and customer that payment went through"""
    from addresses.events import ORDER_PAYMENT_COMPLETED, ORDER_PREPARING

    # Customer: payment received
    customer_event = build_order_event(
        ORDER_PAYMENT_COMPLETED,
        order,
        message="Payment received! Your order is being prepared."
    )
    broadcast_to_order_group(order.id, customer_event)

    # Branch: start preparing
    branch_event = build_order_event(
        ORDER_PREPARING,
        order,
        message="Payment confirmed. Start preparing the order."
    )
    broadcast_to_branch(order.branch_id, branch_event)


def notify_driver_assigned(order):
    """
    Notify customer + branch that a driver is coming,
    AND notify the specific driver they've been assigned.
    """
    from addresses.events import ORDER_DRIVER_ASSIGNED

    driver_name = order.driver.user.name if order.driver else "Driver"

    # Customer + branch (via order group)
    order_event = build_order_event(
        ORDER_DRIVER_ASSIGNED,
        order,
        driver_id=order.driver_id,
        driver_name=driver_name,
        message=f"{driver_name} is on the way to pick up your order."
    )
    broadcast_to_order_group(order.id, order_event)
    broadcast_to_branch(order.branch_id, order_event)

    # Driver: personal notification so they know they got assigned
    driver_event = build_order_event(
        ORDER_DRIVER_ASSIGNED,
        order,
        message="You have been assigned a new order. Head to the restaurant!"
    )
    broadcast_to_specific_drivers([order.driver_id], driver_event)


def notify_order_picked_up(order):
    """Notify customer and branch when driver picks up the order"""
    from addresses.events import ORDER_PICKED_UP

    event_data = build_order_event(
        ORDER_PICKED_UP,
        order,
        message="Your order has been picked up and is on the way!"
    )
    broadcast_to_order_group(order.id, event_data)
    broadcast_to_branch(order.branch_id, event_data)


def notify_order_delivered(order):
    """Notify customer, branch, and driver when order is delivered"""
    from addresses.events import ORDER_DELIVERED

    event_data = build_order_event(
        ORDER_DELIVERED,
        order,
        message="Order delivered successfully! Thank you for your order."
    )
    # Customer gets it via order group
    broadcast_to_order_group(order.id, event_data)
    # Branch needs to know for their dashboard
    # broadcast_to_branch(order.branch_id, event_data)
    # Driver gets confirmation on their personal group
    if order.driver_id:
        broadcast_to_specific_drivers([order.driver_id], build_order_event(
            ORDER_DELIVERED,
            order,
            message="Delivery confirmed! You are now available for new orders."
        ))


def notify_order_cancelled(order, reason=None, cancelled_by=None):
    """Notify all parties: customer (order group), branch, and driver if assigned"""
    from addresses.events import ORDER_CANCELLED

    event_data = build_order_event(
        ORDER_CANCELLED,
        order,
        reason=reason,
        cancelled_by=cancelled_by,
        message=f"Order cancelled. {reason or ''}"
    )
    broadcast_to_order_group(order.id, event_data)
    broadcast_to_branch(order.branch_id, event_data)

    # If a driver was already assigned, tell them too
    if order.driver_id:
        broadcast_to_specific_drivers([order.driver_id], build_order_event(
            ORDER_CANCELLED,
            order,
            message="The order you were assigned has been cancelled."
        ))
