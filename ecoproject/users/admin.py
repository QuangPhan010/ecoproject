# Register your models here.
from django.contrib import admin
from .models import (
    Profile,
    PointExchange,
    MysteryBoxHistory,
    RewardVoucherOption,
    MysteryBoxRewardOption,
)
# Register your models here.
admin.site.register(Profile)
admin.site.register(PointExchange)
admin.site.register(MysteryBoxHistory)


@admin.register(RewardVoucherOption)
class RewardVoucherOptionAdmin(admin.ModelAdmin):
    list_display = ("name", "cost_points", "discount", "max_discount", "valid_days", "active", "sort_order")
    list_filter = ("active",)
    search_fields = ("name",)
    ordering = ("sort_order", "id")


@admin.register(MysteryBoxRewardOption)
class MysteryBoxRewardOptionAdmin(admin.ModelAdmin):
    list_display = ("name", "box_tier", "reward_type", "weight", "active", "sort_order")
    list_filter = ("active", "box_tier", "reward_type")
    search_fields = ("name",)
    ordering = ("sort_order", "id")
