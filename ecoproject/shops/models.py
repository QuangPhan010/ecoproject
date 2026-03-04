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
    available = models.BooleanField(default=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    
    def __str__(self):
        return self.name

    def average_rating(self):
        return self.reviews.filter(parent__isnull=True).aggregate(avg=Avg("rating"))["avg"] or 0
    
    def rating_count(self):
        return self.reviews.filter(parent__isnull=True).count()

    
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
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Processing', 'Processing'),
        ('Shipped', 'Shipped'),
        ('Delivered', 'Delivered'),
        ('Cancelled', 'Cancelled'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders')
    address = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    total_price = models.IntegerField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    paid = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
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

    PAYMENT_CHOICES = (
        ('COD', 'Thanh toán khi nhận hàng'),
        ('BANK', 'Chuyển khoản ngân hàng'),
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

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'Order {self.id}'


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


from django.core.validators import MinValueValidator, MaxValueValidator


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


