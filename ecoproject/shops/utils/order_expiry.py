from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from shops.models import Order, Product, OrderStatusLog


def expire_stale_pending_orders(expire_hours=3, batch_size=200, logger=None):
    """
    Auto-cancel stale pending orders and release reserved stock.
    Returns number of expired orders.
    """
    cutoff = timezone.now() - timedelta(hours=expire_hours)
    stale_ids = list(
        Order.objects
        .filter(status="Pending", paid=False, created_at__lte=cutoff)
        .values_list("id", flat=True)[:batch_size]
    )

    expired_count = 0
    for order_id in stale_ids:
        with transaction.atomic():
            order = (
                Order.objects
                .select_for_update()
                .prefetch_related("items")
                .filter(id=order_id)
                .first()
            )
            if not order:
                continue
            if order.status != "Pending" or order.paid or order.created_at > cutoff:
                continue

            order_items = list(order.items.all())
            product_ids = [item.product_id for item in order_items]
            locked_products = Product.objects.select_for_update().filter(id__in=product_ids)
            product_map = {product.id: product for product in locked_products}

            for item in order_items:
                product = product_map.get(item.product_id)
                if not product:
                    continue
                product.reserved_stock = max(product.reserved_stock - item.quantity, 0)
                product.save(update_fields=["reserved_stock"])

            order.status = "Cancelled"
            order.save(update_fields=["status", "updated_at"])
            OrderStatusLog.objects.create(
                order=order,
                changed_by=None,
                from_status="Pending",
                to_status="Cancelled",
                source="auto_expire",
            )
            expired_count += 1

    if expired_count and logger:
        logger.info("Auto-expired %s stale pending orders.", expired_count)

    return expired_count
