from django.db.models import Sum
from shops.models import Order
from users.models import Profile


# 10.000đ = 1 point
POINT_RATE = 10000


def calculate_points(user):

    total_spent = (
        Order.objects
        .filter(user=user, paid=True)
        .aggregate(total=Sum("total_price"))["total"]
    ) or 0

    points = total_spent // POINT_RATE

    return points


def calculate_rank(points):

    if points >= 50000:
        return Profile.RANK_LEGEND

    elif points >= 25000:
        return Profile.RANK_ELITE

    elif points >= 12000:
        return Profile.RANK_DIAMOND

    elif points >= 6000:
        return Profile.RANK_PLATINUM

    elif points >= 3000:
        return Profile.RANK_GOLD

    elif points >= 1500:
        return Profile.RANK_PREMIUM

    elif points >= 700:
        return Profile.RANK_REGULAR

    elif points >= 300:
        return Profile.RANK_SHOPPER

    elif points >= 100:
        return Profile.RANK_EXPLORER

    return Profile.RANK_NEWBIE


def update_user_rank_realtime(user):

    profile = user.profile

    earned_points = calculate_points(user)

    new_rank = calculate_rank(earned_points)

    updated = False

    # Sync spendable points by delta from lifetime earned points.
    points_delta = earned_points - profile.lifetime_points
    if points_delta != 0:
        profile.points = max(0, profile.points + points_delta)
        profile.lifetime_points = earned_points
        updated = True
    elif profile.lifetime_points != earned_points:
        profile.lifetime_points = earned_points
        updated = True

    if profile.rank != new_rank:
        profile.rank = new_rank
        updated = True

    if updated:
        profile.save()

    return profile
