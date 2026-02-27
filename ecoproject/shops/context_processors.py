def cart_context(request):
    cart = request.session.get('cart', {})
    cart_items_count = len(cart)
    return {
        'cart_items_count': cart_items_count,
        'cart': cart
    }
