from django.utils import timezone
from .models import Coupon, WishlistItem, UserNotification
from django.core.cache import cache


def cart_context(request):
    cart = request.session.get('cart', {})
    cart_items_count = len(cart)
    compare_items_count = len(request.session.get("compare_products", []))
    wishlist_items_count = 0
    navbar_owned_vouchers = []
    navbar_notifications = []
    navbar_unread_notifications_count = 0

    if request.user.is_authenticated:
        cache_key = f"wishlist_items_count:{request.user.id}"
        cached_count = cache.get(cache_key)
        if cached_count is None:
            cached_count = WishlistItem.objects.filter(user=request.user).count()
            cache.set(cache_key, cached_count, 60)
        wishlist_items_count = cached_count

        now = timezone.now()
        navbar_owned_vouchers = list(
            Coupon.objects
            .filter(
                owner=request.user,
                active=True,
                valid_from__lte=now,
                valid_to__gte=now,
            )
            .exclude(couponusage__user=request.user)
            .order_by("valid_to", "id")[:8]
        )
        navbar_notifications = list(
            UserNotification.objects
            .filter(user=request.user)
            .order_by("-created_at")[:8]
        )
        navbar_unread_notifications_count = UserNotification.objects.filter(
            user=request.user,
            is_read=False,
        ).count()

    return {
        'cart_items_count': cart_items_count,
        'compare_items_count': compare_items_count,
        'wishlist_items_count': wishlist_items_count,
        'cart': cart,
        'navbar_owned_vouchers': navbar_owned_vouchers,
        'navbar_owned_vouchers_count': len(navbar_owned_vouchers),
        'navbar_notifications': navbar_notifications,
        'navbar_unread_notifications_count': navbar_unread_notifications_count,
    }
