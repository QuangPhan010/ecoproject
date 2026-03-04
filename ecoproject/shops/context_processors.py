from .models import WishlistItem


def cart_context(request):
    cart = request.session.get('cart', {})
    cart_items_count = len(cart)
    compare_items_count = len(request.session.get("compare_products", []))
    wishlist_items_count = 0

    if request.user.is_authenticated:
        wishlist_items_count = WishlistItem.objects.filter(user=request.user).count()

    return {
        'cart_items_count': cart_items_count,
        'compare_items_count': compare_items_count,
        'wishlist_items_count': wishlist_items_count,
        'cart': cart
    }
