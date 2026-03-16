from django.contrib import admin, messages
from .models import (
    Product, FlashSale, ProductOption, ProductColor, Category,
    Order, OrderItem, Coupon, WishlistItem, OrderStatusLog, AfterSalesRequest,
    UserNotification,
)
from .views import _apply_status_change

# ================= PRODUCT =================

class ProductOptionInline(admin.TabularInline):
    model = ProductOption
    extra = 1


class ProductColorInline(admin.TabularInline):
    model = ProductColor
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


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
        readonly = ["paid"]
        # Allow admin to move Delivered -> ReturnRequested -> Returned.
        # Lock status only once shipped (handed to carrier) or fully returned.
        if obj and obj.status in [Order.STATUS_SHIPPED, Order.STATUS_RETURNED]:
            readonly.append("status")
        return tuple(readonly)

    def save_model(self, request, obj, form, change):
        if not change:
            super().save_model(request, obj, form, change)
            return

        current = Order.objects.get(pk=obj.pk)

        # Ensure status changes in Django Admin follow the same business flow as website.
        if "status" in form.changed_data and obj.status != current.status:
            ok, error_msg = _apply_status_change(
                current,
                obj.status,
                changed_by=request.user,
                source="admin_site",
            )
            if not ok:
                self.message_user(
                    request,
                    f"Không thể cập nhật đơn #{obj.pk}: {error_msg}",
                    level=messages.ERROR,
                )
                return

            other_fields = [f for f in form.changed_data if f not in {"status", "paid"}]
            if other_fields:
                for field in other_fields:
                    setattr(current, field, getattr(obj, field))
                current.save(update_fields=other_fields + ["updated_at"])

            obj.status = current.status
            obj.paid = current.paid
            return

        super().save_model(request, obj, form, change)

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'discount', 'max_discount',
        'used_count', 'usage_limit',
        'active', 'valid_from', 'valid_to'
    )
    list_filter = ('active',)
    search_fields = ('code',)


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "product", "created_at")
    search_fields = ("user__username", "product__name")
    list_filter = ("created_at",)


@admin.register(OrderStatusLog)
class OrderStatusLogAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "from_status", "to_status", "source", "changed_by", "changed_at")
    list_filter = ("source", "from_status", "to_status", "changed_at")
    search_fields = ("order__id", "changed_by__username", "changed_by__email")


@admin.register(AfterSalesRequest)
class AfterSalesRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "request_type",
        "status",
        "refund_amount",
        "contact_name",
        "processed_by",
        "created_at",
    )
    list_filter = ("request_type", "status", "created_at")
    search_fields = ("order__id", "contact_name", "contact_email", "contact_phone")


@admin.register(UserNotification)
class UserNotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "notification_type", "title", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("user__username", "user__email", "title", "message")
