"""
Celery tasks for timeouts and background jobs
Place in: orders/tasks.py
"""
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from django.db.models import Q
from .models import Order, DriverProfile, OrderEvent
from addresses.models import DriverLocation
from .websocket_utils import (
    broadcast_to_order_group, 
    broadcast_to_branch,
    notify_order_cancelled,
    notify_order_ready,
    broadcast_to_specific_drivers
)
from addresses.events import *
from .gis_utils import find_nearest_available_drivers
import logging

logger = logging.getLogger(__name__)


# ===== TIMEOUT TASKS =====

@shared_task(name='orders.check_branch_confirmation_timeout')
def check_branch_confirmation_timeout(order_id):
    """
    Check if branch confirmed the order within timeout period
    Called after BRANCH_CONFIRMATION_TIMEOUT seconds from order creation
    """
    try:
        order = Order.objects.select_related('branch', 'orderer').get(id=order_id)
        
        # If still pending, cancel it
        if order.status == 'pending':
            logger.info(f"Order {order.id} timed out - branch did not confirm")
            
            order.status = 'cancelled'
            order.save(update_fields=['status', 'last_modified_at'])
            
            # Log event
            OrderEvent.objects.create(
                order=order,
                event_type='cancelled',
                actor_type='system',
                old_status='pending',
                new_status='cancelled',
                metadata={'reason': 'branch_timeout'}
            )
            
            # Notify customer and branch
            notify_order_cancelled(
                order,
                reason="Restaurant did not respond in time",
                cancelled_by="system"
            )
            
            return f"Order {order.id} cancelled due to branch timeout"
        
        return f"Order {order.id} was already confirmed/cancelled"
        
    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found for timeout check")
        return None


@shared_task(name='orders.check_payment_timeout')
def check_payment_timeout(order_id):
    """
    Check if payment was completed within timeout period
    Called after PAYMENT_TIMEOUT seconds from order confirmation
    """
    try:
        order = Order.objects.select_related('branch', 'orderer').get(id=order_id)
        
        # If still waiting for payment, cancel it
        if order.status in ['confirmed', 'payment_pending']:
            logger.info(f"Order {order.id} timed out - payment not completed")
            
            order.status = 'cancelled'
            order.save(update_fields=['status', 'last_modified_at'])
            
            # Log event
            OrderEvent.objects.create(
                order=order,
                event_type='cancelled',
                actor_type='system',
                old_status=order.status,
                new_status='cancelled',
                metadata={'reason': 'payment_timeout'}
            )
            
            # Notify all parties
            notify_order_cancelled(
                order,
                reason="Payment not completed in time",
                cancelled_by="system"
            )
            
            return f"Order {order.id} cancelled due to payment timeout"
        
        return f"Order {order.id} payment was completed"
        
    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found for payment timeout check")
        return None


@shared_task(name='orders.check_driver_acceptance_timeout')
def check_driver_acceptance_timeout(order_id, driver_id):
    """
    Check if driver accepted the order within timeout period
    If not, find next available driver
    """
    try:
        order = Order.objects.select_related('branch', 'driver').get(id=order_id)
        
        # If still waiting for this driver
        if order.status == 'driver_assigned' and order.driver_id == driver_id:
            logger.info(f"Driver {driver_id} timed out for order {order.id}")
            
            # Log event
            OrderEvent.objects.create(
                order=order,
                event_type='driver_rejected',
                actor_type='system',
                metadata={
                    'reason': 'timeout',
                    'driver_id': driver_id
                }
            )
            
            # Try to find another driver
            find_and_assign_driver.delay(order_id, excluded_driver_ids=[driver_id])
            
            return f"Driver {driver_id} timed out, finding alternative"
        
        return f"Order {order.id} was already accepted/cancelled"
        
    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found for driver timeout check")
        return None


@shared_task(name='orders.check_driver_pickup_timeout')
def check_driver_pickup_timeout(order_id):
    """
    Check if driver picked up the order within reasonable time
    """
    try:
        order = Order.objects.select_related('branch', 'driver').get(id=order_id)
        
        # If still not picked up
        if order.status in ['driver_assigned', 'ready']:
            logger.warning(f"Driver taking too long to pickup order {order.id}")
            
            # Could reassign or notify support
            # For now, just log and notify
            broadcast_to_order_group(order.id, {
                'type': 'order.warning',
                'message': 'Driver is taking longer than expected. We are monitoring the situation.'
            })
            
            return f"Pickup delay warning sent for order {order.id}"
        
        return f"Order {order.id} was picked up"
        
    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found for pickup timeout check")
        return None


# ===== DRIVER MATCHING TASKS =====

@shared_task(name='orders.find_and_assign_driver')
def find_and_assign_driver(order_id, excluded_driver_ids=None):
    """
    Find nearest available driver and assign to order
    """
    try:
        order = Order.objects.select_related('branch').get(id=order_id)
        
        if order.status != 'ready':
            logger.info(f"Order {order.id} is not ready for driver assignment")
            return None
        
        # Get branch location
        branch_location = order.branch.location
        
        # Find nearest drivers
        available_drivers = find_nearest_available_drivers(
            branch_location,
            max_drivers=settings.MAX_DRIVERS_TO_NOTIFY
        )
        
        # Filter out excluded drivers
        if excluded_driver_ids:
            available_drivers = [
                (driver, distance) for driver, distance in available_drivers
                if driver.id not in excluded_driver_ids
            ]
        
        if not available_drivers:
            logger.error(f"No available drivers found for order {order.id}")
            
            # Notify customer
            broadcast_to_order_group(order.id, {
                'type': ORDER_DRIVER_NOT_FOUND,
                'message': 'No available drivers nearby. Still searching...'
            })
            
            # Retry after 2 minutes
            find_and_assign_driver.apply_async(
                args=[order_id, excluded_driver_ids],
                countdown=120
            )
            return f"No drivers available, will retry"
        
        # Assign to nearest driver
        driver, distance = available_drivers[0]
        
        order.driver = driver
        order.status = 'driver_assigned'
        order.assigned_at = timezone.now()
        order.save(update_fields=['driver', 'status', 'assigned_at', 'last_modified_at'])
        
        # Update driver status
        driver.is_available = False
        driver.current_order = order
        driver.save(update_fields=['is_available', 'current_order'])
        
        # Log event
        OrderEvent.objects.create(
            order=order,
            event_type='driver_assigned',
            actor_type='system',
            old_status='ready',
            new_status='driver_assigned',
            metadata={
                'driver_id': driver.id,
                'distance_km': float(distance)
            }
        )
        
        # Notify driver
        broadcast_to_specific_drivers([driver.id], {
            'type': ORDER_DRIVER_ASSIGNED,
            'order_id': order.id,
            'order_number': order.order_number,
            'branch': {
                'name': order.branch.name,
                'location': {
                    'lat': order.branch.location.y,
                    'lng': order.branch.location.x
                }
            },
            'distance_km': float(distance),
            'message': f'New order #{order.order_number} assigned to you!'
        })
        
        # Notify customer and branch
        from .websocket_utils import notify_driver_assigned
        notify_driver_assigned(order)
        
        # Start driver acceptance timeout
        check_driver_acceptance_timeout.apply_async(
            args=[order.id, driver.id],
            countdown=settings.DRIVER_ACCEPTANCE_TIMEOUT
        )
        
        logger.info(f"Driver {driver.id} assigned to order {order.id}")
        return f"Driver {driver.id} assigned to order {order.id}"
        
    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found for driver assignment")
        return None


@shared_task(name='orders.notify_multiple_drivers')
def notify_multiple_drivers(order_id, driver_ids):
    """
    Notify multiple drivers about an available order (alternative approach)
    First to accept wins
    """
    try:
        order = Order.objects.select_related('branch').get(id=order_id)
        
        # Broadcast to specific drivers
        broadcast_to_specific_drivers(driver_ids, {
            'type': 'order.available',
            'order_id': order.id,
            'order_number': order.order_number,
            'branch': {
                'name': order.branch.name,
                'location': {
                    'lat': order.branch.location.y,
                    'lng': order.branch.location.x
                }
            },
            'message': f'Order #{order.order_number} is available for pickup!'
        })
        
        return f"Notified {len(driver_ids)} drivers about order {order.id}"
        
    except Order.DoesNotExist:
        return None


# ===== PERIODIC CLEANUP TASKS =====

@shared_task(name='drivers.cleanup_stale_driver_locations')
def cleanup_stale_driver_locations():
    """
    Mark stale driver locations as offline
    Runs every 5 minutes via Celery Beat
    """
    stale_threshold = timezone.now() - timezone.timedelta(
        seconds=settings.DRIVER_LOCATION_STALE_THRESHOLD
    )
    
    # Mark stale locations as offline
    stale_count = DriverLocation.objects.filter(
        is_online=True,
        last_updated__lt=stale_threshold
    ).update(is_online=False)
    
    # Also update driver profiles
    DriverProfile.objects.filter(
        is_online=True,
        last_location_update__lt=stale_threshold
    ).update(is_online=False, is_available=False)
    
    logger.info(f"Marked {stale_count} stale driver locations as offline")
    return f"Cleaned up {stale_count} stale locations"


@shared_task(name='orders.check_all_payment_timeouts')
def check_all_payment_timeouts():
    """
    Check all orders waiting for payment
    Runs every minute via Celery Beat
    """
    timeout_threshold = timezone.now() - timezone.timedelta(
        seconds=settings.PAYMENT_TIMEOUT
    )
    
    # Find orders stuck in payment_pending or confirmed
    stuck_orders = Order.objects.filter(
        Q(status='payment_pending') | Q(status='confirmed'),
        payment_initialized_at__lt=timeout_threshold,
        payment_completed_at__isnull=True
    )
    
    cancelled_count = 0
    for order in stuck_orders:
        # Cancel the order
        order.status = 'cancelled'
        order.save(update_fields=['status', 'last_modified_at'])
        
        # Log event
        OrderEvent.objects.create(
            order=order,
            event_type='cancelled',
            actor_type='system',
            old_status=order.status,
            new_status='cancelled',
            metadata={'reason': 'payment_timeout_batch'}
        )
        
        # Notify
        notify_order_cancelled(
            order,
            reason="Payment not completed in time",
            cancelled_by="system"
        )
        
        cancelled_count += 1
    
    logger.info(f"Cancelled {cancelled_count} orders due to payment timeout")
    return f"Cancelled {cancelled_count} orders"


# ===== PAYMENT VERIFICATION TASKS =====

@shared_task(name='orders.verify_payment_status')
def verify_payment_status(order_id):
    """
    Verify payment status with Paystack (if webhook failed)
    """
    try:
        from .models import Transaction
        
        order = Order.objects.get(id=order_id)
        
        if not order.payment_reference:
            return "No payment reference"
        
        # Verify with Paystack
        result = Transaction.verify(order.payment_reference)
        
        if result['status'] and result['data']['status'] == 'success':
            # Payment successful, update order
            if order.status in ['payment_pending', 'confirmed']:
                order.status = 'preparing'
                order.payment_completed_at = timezone.now()
                order.save(update_fields=['status', 'payment_completed_at', 'last_modified_at'])
                
                # Notify all parties
                from .websocket_utils import notify_payment_completed
                notify_payment_completed(order)
                
                logger.info(f"Payment verified for order {order.id}")
                return f"Payment verified for order {order.id}"
        
        return f"Payment not completed for order {order.id}"
        
    except Order.DoesNotExist:
        return f"Order {order_id} not found"
    except Exception as e:
        logger.error(f"Error verifying payment for order {order_id}: {e}")
        return f"Error: {str(e)}"