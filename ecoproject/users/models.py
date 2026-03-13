from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from datetime import timedelta


# Create your models here.
class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL , on_delete=models.CASCADE)
    photo = models.ImageField(upload_to='users/%Y/%m/%d/', blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    # Available points that users can spend on rewards.
    points = models.IntegerField(default=0)
    # Lifetime earned points used for rank calculation.
    lifetime_points = models.IntegerField(default=0)
    # Play credits exchanged from points.
    minigame_plays = models.IntegerField(default=0)
    # Consecutive Standard Box turns without drawing a voucher.
    standard_voucher_pity = models.PositiveSmallIntegerField(default=0)
    # Consecutive Premium Box turns without drawing a voucher.
    premium_voucher_pity = models.PositiveSmallIntegerField(default=0)

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


class PointExchange(models.Model):
    TYPE_VOUCHER = "VOUCHER"
    TYPE_MINIGAME = "MINIGAME"

    TYPE_CHOICES = (
        (TYPE_VOUCHER, "Doi voucher"),
        (TYPE_MINIGAME, "Doi luot choi minigame"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="point_exchanges"
    )
    exchange_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    points_spent = models.PositiveIntegerField()
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user.username} - {self.exchange_type} - {self.points_spent}"


class MysteryBoxHistory(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mystery_box_histories"
    )
    open_count = models.PositiveSmallIntegerField()
    rewards = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user.username} - open {self.open_count} boxes"


class RewardVoucherOption(models.Model):
    name = models.CharField(max_length=120)
    cost_points = models.PositiveIntegerField(default=100)
    discount = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    max_discount = models.PositiveIntegerField(default=0)
    valid_days = models.PositiveSmallIntegerField(default=7)
    active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")

    def __str__(self):
        return f"{self.name} ({self.cost_points} points)"


class MysteryBoxRewardOption(models.Model):
    BOX_STANDARD = "STANDARD"
    BOX_PREMIUM = "PREMIUM"
    BOX_CHOICES = (
        (BOX_STANDARD, "Standard Box"),
        (BOX_PREMIUM, "Premium Box"),
    )

    TYPE_POINTS = "POINTS"
    TYPE_PLAYS = "PLAYS"
    TYPE_VOUCHER = "VOUCHER"
    TYPE_EMPTY = "EMPTY"

    TYPE_CHOICES = (
        (TYPE_POINTS, "Cong diem"),
        (TYPE_PLAYS, "Cong luot choi"),
        (TYPE_VOUCHER, "Voucher"),
        (TYPE_EMPTY, "Khong trung"),
    )

    name = models.CharField(max_length=120)
    box_tier = models.CharField(max_length=20, choices=BOX_CHOICES, default=BOX_STANDARD)
    reward_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    points_value = models.PositiveIntegerField(default=0)
    plays_value = models.PositiveIntegerField(default=0)
    voucher_discount = models.PositiveSmallIntegerField(default=0)
    voucher_max_discount = models.PositiveIntegerField(default=0)
    voucher_valid_days = models.PositiveSmallIntegerField(default=0)
    weight = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")

    def __str__(self):
        return f"{self.name} [{self.box_tier}] ({self.reward_type}, w={self.weight})"


class PasswordResetOTP(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_otps",
    )
    email = models.EmailField()
    code = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["email", "-created_at"]),
            models.Index(fields=["user", "used", "-created_at"]),
        ]

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def resend_available_in(self, cooldown_seconds=60):
        elapsed = (timezone.now() - self.created_at).total_seconds()
        return max(0, int(cooldown_seconds - elapsed))

    @classmethod
    def build_expiry(cls, minutes=10):
        return timezone.now() + timedelta(minutes=minutes)
