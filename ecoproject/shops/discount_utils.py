def calculate_rank_discount(user, subtotal):

    profile = user.profile

    benefits = profile.get_rank_benefits()

    percent = benefits["discount"]

    max_discount = benefits["max_discount"]

    discount = subtotal * percent / 100

    if discount > max_discount:
        discount = max_discount

    return int(discount)
