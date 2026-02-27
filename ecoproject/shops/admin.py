from django.contrib import admin
from .models import (
    Product, FlashSale, ProductOption, ProductColor,
    Order, OrderItem, Coupon
)

# ================= PRODUCT =================

class ProductOptionInline(admin.TabularInline):
    model = ProductOption
    extra = 1


class ProductColorInline(admin.TabularInline):
    model = ProductColor
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductOptionInline, ProductColorInline]


admin.site.register(FlashSale)

# ================= ORDER =================

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'price', 'quantity')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    # 👉 HIỂN THỊ DANH SÁCH
    list_display = (
        'id',
        'user',
        'phone',
        'total_price',
        'payment_method',
        'paid',
        'status',
        'created_at',
    )

    # 👉 CHỈNH TRỰC TIẾP TRÊN LIST
    list_editable = (
        'status',
        'paid',
    )

    # 👉 LINK CHI TIẾT
    list_display_links = ('id', 'user')

    # 👉 BỘ LỌC
    list_filter = (
        'status',
        'payment_method',
        'paid',
        'created_at',
    )

    # 👉 TÌM KIẾM
    search_fields = (
        'user__username',
        'phone',
        'address',
    )

    ordering = ('-created_at',)

    inlines = [OrderItemInline]
def get_readonly_fields(self, request, obj=None):
    if obj and obj.status in ['Shipped', 'Delivered']:
        return ('status',)
    return ()

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'discount', 'max_discount',
        'used_count', 'usage_limit',
        'active', 'valid_from', 'valid_to'
    )
    list_filter = ('active',)
    search_fields = ('code',)