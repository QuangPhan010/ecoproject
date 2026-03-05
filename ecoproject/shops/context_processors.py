from .models import WishlistItem
from django.core.cache import cache


def cart_context(request):
    cart = request.session.get('cart', {})
    cart_items_count = len(cart)
    compare_items_count = len(request.session.get("compare_products", []))
    wishlist_items_count = 0

    if request.user.is_authenticated:
        cache_key = f"wishlist_items_count:{request.user.id}"
        cached_count = cache.get(cache_key)
        if cached_count is None:
            cached_count = WishlistItem.objects.filter(user=request.user).count()
            cache.set(cache_key, cached_count, 60)
        wishlist_items_count = cached_count

    return {
        'cart_items_count': cart_items_count,
        'compare_items_count': compare_items_count,
        'wishlist_items_count': wishlist_items_count,
        'cart': cart
    }
