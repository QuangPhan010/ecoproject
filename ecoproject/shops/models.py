from django.db import models
from django.utils import timezone
from django.conf import settings
from django.db.models import Avg
from django.core.validators import MinValueValidator, MaxValueValidator
import random
import uuid




# Create your models here.
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    price = models.IntegerField()
    old_price = models.IntegerField(null=True, blank=True)
    image = models.URLField(max_length=500)
    sold = models.IntegerField(default=0)
    description = models.TextField(null=True, blank=True)
    stock = models.IntegerField(default=0)
    reserved_stock = models.IntegerField(default=0)
    available = models.BooleanField(default=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    
    def __str__(self):
        return self.name

    def average_rating(self):
        return self.reviews.filter(parent__isnull=True).aggregate(avg=Avg("rating"))["avg"] or 0
    
    def rating_count(self):
        return self.reviews.filter(parent__isnull=True).count()

    @property
    def available_stock(self):
        return max(self.stock - self.reserved_stock, 0)

    class Meta:
        indexes = [
            models.Index(fields=["available"]),
            models.Index(fields=["available", "reserved_stock"]),
        ]

    
class FlashSale(models.Model):
    title = models.CharField(max_length=200)
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

class ProductOption(models.Model):
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='options')
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.product.name} - {self.name}"


class ProductColor(models.Model):
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='colors')
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=20)  # ví dụ: #ff0000

    def __str__(self):
        return f"{self.product.name} - {self.name}"
    
class Review(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="reviews"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="replies",
        on_delete=models.CASCADE
    )

    rating = models.PositiveSmallIntegerField(
        default=5
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product.name} - {self.user}"

    @property
    def likes_count(self):
        return self.reactions.filter(is_like=True).count()

    @property
    def dislikes_count(self):
        return self.reactions.filter(is_like=False).count()
    

class ReviewReaction(models.Model):
    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name="reactions"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_like = models.BooleanField()

    class Meta:
        unique_together = ("review", "user")


class Order(models.Model):
    STATUS_PENDING = "Pending"
    STATUS_PROCESSING = "Processing"
    STATUS_SHIPPED = "Shipped"
    STATUS_DELIVERED = "Delivered"
    STATUS_CANCELLED = "Cancelled"
    STATUS_RETURN_REQUESTED = "ReturnRequested"
    STATUS_RETURNED = "Returned"

    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_SHIPPED, "Shipped"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_RETURN_REQUESTED, "Yêu cầu hoàn trả"),
        (STATUS_RETURNED, "Đã hoàn trả"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders', null=True, blank=True)
    guest_name = models.CharField(max_length=150, blank=True)
    guest_email = models.EmailField(blank=True)
    address = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    total_price = models.IntegerField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    paid = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    shipping_method = models.CharField(max_length=50, default='Standard')
    shipping_cost = models.IntegerField(default=0)
    coupon = models.ForeignKey('Coupon', on_delete=models.SET_NULL, null=True, blank=True)
    discount = models.IntegerField(default=0)
    qr_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False
    )
    tracking_code = models.CharField(
        max_length=20,
        default='',
        blank=True
    )
    cancel_reason = models.TextField(blank=True)

    PAYMENT_CHOICES = (
        ('COD', 'Thanh toán khi nhận hàng'),
        ('BANK', 'Chuyển khoản ngân hàng'),
        ('WALLET', 'Thanh toán bằng ví hoàn trả'),
        ('MOMO', 'Chuyển khoản ví điện tử MoMo'),
        ('VNPAY', 'Chuyển khoản ví điện tử VNPAY'),
    )

    payment_method = models.CharField(
        max_length=10,
        choices=PAYMENT_CHOICES,
        default='COD'
    )
    rank_discount = models.IntegerField(default=0)


    def save(self, *args, **kwargs):
        if not self.tracking_code:
            self.tracking_code = f"QSHOP{random.randint(1000, 9999)}"
        super().save(*args, **kwargs)

    @property
    def customer_name(self):
        if self.user_id:
            return self.user.get_full_name() or self.user.username
        return self.guest_name or "Khach hang"

    @property
    def customer_email(self):
        if self.user_id:
            return self.user.email
        return self.guest_email

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["paid", "status"]),
            models.Index(fields=["user", "status", "-created_at"]),
        ]

    def __str__(self):
        return f'Order {self.id}'


class OrderStatusLog(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="status_logs",
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_status_logs",
    )
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    source = models.CharField(max_length=50, default="system")
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-changed_at",)
        indexes = [
            models.Index(fields=["order", "-changed_at"]),
            models.Index(fields=["source", "-changed_at"]),
            models.Index(fields=["changed_by", "-changed_at"]),
        ]

    def __str__(self):
        return f"Order #{self.order_id}: {self.from_status} -> {self.to_status}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='order_items')
    price = models.IntegerField()
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return str(self.id)

    @property
    def total_cost(self):
        return self.price * self.quantity


class AfterSalesRequest(models.Model):
    TYPE_EXCHANGE = "EXCHANGE"
    TYPE_RETURN = "RETURN"
    TYPE_REFUND = "REFUND"
    TYPE_CHOICES = (
        (TYPE_EXCHANGE, "Đổi hàng"),
        (TYPE_RETURN, "Hoàn trả hàng"),
        (TYPE_REFUND, "Hoàn tiền"),
    )

    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Chờ xử lý"),
        (STATUS_APPROVED, "Đã duyệt"),
        (STATUS_REJECTED, "Từ chối"),
        (STATUS_COMPLETED, "Hoàn tất"),
    )

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="after_sales_requests")
    request_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reason = models.TextField()
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="after_sales_requests",
    )
    contact_name = models.CharField(max_length=150, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    resolution_note = models.TextField(blank=True)
    refund_amount = models.IntegerField(default=0)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_after_sales_requests",
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["request_type", "-created_at"]),
            models.Index(fields=["order", "-created_at"]),
        ]

    def __str__(self):
        return f"After-sales #{self.id} - Order #{self.order_id}"


class AfterSalesRequestImage(models.Model):
    after_sales_request = models.ForeignKey(
        AfterSalesRequest,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="after_sales/%Y/%m/%d/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-uploaded_at",)

    def __str__(self):
        return f"Image #{self.id} for request #{self.after_sales_request_id}"


class UserNotification(models.Model):
    TYPE_ORDER_STATUS = "ORDER_STATUS"
    TYPE_AFTER_SALES = "AFTER_SALES"
    TYPE_VOUCHER = "VOUCHER"
    TYPE_SYSTEM = "SYSTEM"
    TYPE_CHOICES = (
        (TYPE_ORDER_STATUS, "Trạng thái đơn hàng"),
        (TYPE_AFTER_SALES, "Hậu mãi"),
        (TYPE_VOUCHER, "Voucher"),
        (TYPE_SYSTEM, "Hệ thống"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_SYSTEM)
    title = models.CharField(max_length=160)
    message = models.TextField(blank=True)
    target_url = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["notification_type", "-created_at"]),
        ]

    def __str__(self):
        return f"Notification #{self.id} - {self.user}"


class Coupon(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="owned_coupons"
    )
    code = models.CharField(max_length=50, unique=True)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()

    discount = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)]
    )

    max_discount = models.IntegerField(
        default=0,
        help_text="Số tiền giảm tối đa (0 = không giới hạn)"
    )

    usage_limit = models.PositiveIntegerField(
        default=0,
        help_text="Số lượt dùng tối đa (0 = không giới hạn)"
    )

    used_count = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    categories = models.ManyToManyField(Category, blank=True, help_text="Chọn danh mục sản phẩm để áp dụng voucher (để trống nếu áp dụng cho tất cả)")

    def save(self, *args, **kwargs):
        if self.valid_to < timezone.now():
            self.active = False
        super().save(*args, **kwargs)

    @property
    def is_expired(self):

        now = timezone.now()

        # quá ngày
        if self.valid_to and self.valid_to < now:
            return True

        # hết lượt dùng
        if self.usage_limit > 0 and self.used_count >= self.usage_limit:
            return True

        return False


class CouponUsage(models.Model):
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('coupon', 'user')  # QUAN TRỌNG


class WishlistItem(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist_items"
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="wishlisted_items"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "product")
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user} - {self.product}"


