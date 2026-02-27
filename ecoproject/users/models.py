from django.conf import settings
from django.db import models
from django.contrib.auth.models import User


# Create your models here.
class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL , on_delete=models.CASCADE)
    photo = models.ImageField(upload_to='users/%Y/%m/%d/', blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    points = models.IntegerField(default=0)

    RANK_NEWBIE = "Newbie"
    RANK_EXPLORER = "Explorer"
    RANK_SHOPPER = "Shopper"
    RANK_REGULAR = "Regular"
    RANK_PREMIUM = "Premium"
    RANK_GOLD = "Gold Buyer"
    RANK_PLATINUM = "Platinum Buyer"
    RANK_DIAMOND = "Diamond Buyer"
    RANK_ELITE = "Elite Buyer"
    RANK_LEGEND = "Legend Buyer"

    RANK_CHOICES = (
        (RANK_NEWBIE, "Newbie"),
        (RANK_EXPLORER, "Explorer"),
        (RANK_SHOPPER, "Shopper"),
        (RANK_REGULAR, "Regular"),
        (RANK_PREMIUM, "Premium"),
        (RANK_GOLD, "Gold Buyer"),
        (RANK_PLATINUM, "Platinum Buyer"),
        (RANK_DIAMOND, "Diamond Buyer"),
        (RANK_ELITE, "Elite Buyer"),
        (RANK_LEGEND, "Legend Buyer"),
    )

    rank = models.CharField(
        max_length=30,
        choices=RANK_CHOICES,
        default=RANK_NEWBIE
    )

    def __str__(self):
        return f"{self.user.username} - {self.rank} ({self.points} points)"
    
    def get_rank_icon(self):

        icons = {
            "Newbie": "🌱",
            "Explorer": "🧭",
            "Shopper": "🛍️",
            "Regular": "⭐",
            "Premium": "👑",
            "Gold Buyer": "🥇",
            "Platinum Buyer": "💎",
            "Diamond Buyer": "🔷",
            "Elite Buyer": "🚀",
            "Legend Buyer": "🔥",
        }

        return icons.get(self.rank, "⭐")
    
    def get_rank_color(self):

        colors = {
            "Newbie": "#9ca3af",
            "Explorer": "#22c55e",
            "Shopper": "#3b82f6",
            "Regular": "#6366f1",
            "Premium": "#a855f7",
            "Gold Buyer": "#f59e0b",
            "Platinum Buyer": "#06b6d4",
            "Diamond Buyer": "#0ea5e9",
            "Elite Buyer": "#ef4444",
            "Legend Buyer": "#f97316",
        }

        return colors.get(self.rank, "#6366f1")
    
    def get_rank_benefits(self):

        benefits = {

            "Newbie": {
                "discount": 0,
                "max_discount": 0,
            },

            "Explorer": {
                "discount": 0.5,
                "max_discount": 200_000,
            },

            "Shopper": {
                "discount": 1,
                "max_discount": 500_000,
            },

            "Regular": {
                "discount": 1.5,
                "max_discount": 800_000,
            },

            "Premium": {
                "discount": 2,
                "max_discount": 1_500_000,
            },

            "Gold Buyer": {
                "discount": 3,
                "max_discount": 2_000_000,
            },

            "Platinum Buyer": {
                "discount": 4,
                "max_discount": 3_000_000,
            },

            "Diamond Buyer": {
                "discount": 5,
                "max_discount": 4_000_000,
            },

            "Elite Buyer": {
                "discount": 6,
                "max_discount": 5_000_000,
            },

            "Legend Buyer": {
                "discount": 7,
                "max_discount": 7_000_000,
            },

        }

        return benefits.get(
            self.rank,
            {"discount": 0, "max_discount": 0}
        )
