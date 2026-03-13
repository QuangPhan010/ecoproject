import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from shops.models import Order, OrderItem, Product, Coupon, CouponUsage, Review
from shops.rank_utils import update_user_rank_realtime


class Command(BaseCommand):
    help = "Seed realistic ecommerce orders"

    def add_arguments(self, parser):
        parser.add_argument(
            "--total-orders",
            type=int,
            default=100,
            help="Total orders to generate",
        )

    def handle(self, *args, **options):

        total_orders = options["total_orders"]

        users = list(get_user_model().objects.all())
        products = list(Product.objects.filter(available=True))

        now = timezone.now()

        coupons = list(
            Coupon.objects.filter(
                active=True,
                valid_from__lte=now,
                valid_to__gte=now,
            )
        )

        if not products:
            self.stdout.write(self.style.ERROR("No products found"))
            return

        status_choices = [s for s, _ in Order.STATUS_CHOICES]
        payment_choices = [p for p, _ in Order.PAYMENT_CHOICES]

        guest_names = [
            "Nguyễn Văn A",
            "Trần Thị B",
            "Lê Văn C",
            "Phạm Minh D",
            "Hoàng Gia E",
            "Võ Thanh F",
        ]

        addresses = [
            "123 Nguyễn Trãi, TP.HCM",
            "45 Lê Lợi, TP.HCM",
            "88 Điện Biên Phủ, TP.HCM",
            "22 Trường Chinh, TP.HCM",
            "9 Nguyễn Huệ, TP.HCM",
        ]

        positive_comments = [
            "Sản phẩm rất tốt",
            "Đáng tiền",
            "Chất lượng vượt mong đợi",
            "Shop đóng gói cẩn thận",
            "Giao hàng nhanh",
            "Sẽ mua lại",
        ]

        neutral_comments = [
            "Tạm ổn",
            "Dùng được",
            "Không có gì đặc biệt",
            "Giá hơi cao",
        ]

        negative_comments = [
            "Không giống mô tả",
            "Giao hàng chậm",
            "Chất lượng chưa tốt",
            "Hơi thất vọng",
            "Sản phẩm bị lỗi nhẹ",
        ]

        peak_hours = [
            (9, 11),
            (12, 13),
            (19, 22),
        ]

        def random_rating():
            r = random.random()

            if r < 0.05:
                return 1
            elif r < 0.15:
                return 2
            elif r < 0.30:
                return 3
            elif r < 0.50:
                return 4
            else:
                return 5

        created = 0
        day_offset = 0

        while created < total_orders:

            orders_today = random.randint(6, 10)

            base_date = now - timedelta(days=day_offset)

            for _ in range(orders_today):

                if created >= total_orders:
                    break

                start, end = random.choice(peak_hours)

                created_at = base_date.replace(
                    hour=random.randint(start, end),
                    minute=random.randint(0, 59),
                    second=random.randint(0, 59),
                    microsecond=0,
                )

                with transaction.atomic():

                    picked_products = random.sample(
                        products,
                        random.randint(1, min(4, len(products)))
                    )

                    item_data = []
                    total_price = 0

                    for p in picked_products:

                        qty = random.randint(1, 3)

                        if p.stock < qty:
                            continue

                        p.stock -= qty
                        p.save(update_fields=["stock"])

                        total_price += p.price * qty

                        item_data.append((p, qty))

                    if not item_data:
                        continue

                    status = random.choice(status_choices)

                    is_guest = random.random() < 0.4

                    if is_guest or not users:
                        user = None
                        guest_name = random.choice(guest_names)
                        guest_email = f"guest{random.randint(1000,9999)}@mail.com"
                    else:
                        user = random.choice(users)
                        guest_name = ""
                        guest_email = ""

                    address = random.choice(addresses)
                    phone = "09" + "".join(random.choices("0123456789", k=8))

                    shipping_cost = random.choice([15000, 20000, 30000])

                    coupon = None
                    discount = 0

                    if coupons and random.random() < 0.25:

                        coupon = random.choice(coupons)

                        discount = coupon.discount

                        if coupon.max_discount:
                            discount = min(discount, coupon.max_discount)

                    final_price = total_price + shipping_cost - discount

                    order = Order.objects.create(
                        user=user,
                        guest_name=guest_name,
                        guest_email=guest_email,
                        address=address,
                        phone=phone,
                        total_price=final_price,
                        shipping_method="Standard",
                        shipping_cost=shipping_cost,
                        coupon=coupon,
                        discount=discount,
                        payment_method=random.choice(payment_choices),
                        paid=(status in ["Delivered", "Shipped"]),
                        status=status,
                        created_at=created_at,
                    )

                    for p, qty in item_data:

                        OrderItem.objects.create(
                            order=order,
                            product=p,
                            price=p.price,
                            quantity=qty,
                        )

                    if coupon and user:
                        CouponUsage.objects.get_or_create(
                            coupon=coupon,
                            user=user,
                        )

                    if status == "Delivered" and user and random.random() < 0.7:

                        review_products = random.sample(
                            [p for p, _ in item_data],
                            random.randint(1, len(item_data))
                        )

                        for p in review_products:

                            rating = random_rating()

                            if rating >= 4:
                                comment = random.choice(positive_comments)
                            elif rating == 3:
                                comment = random.choice(neutral_comments)
                            else:
                                comment = random.choice(negative_comments)

                            Review.objects.create(
                                product=p,
                                user=user,
                                rating=rating,
                                content=comment,
                            )

                    if user:
                        update_user_rank_realtime(user)

                created += 1

            day_offset += 1

            self.stdout.write(
                self.style.SUCCESS(f"Created {created} orders...")
            )

        self.stdout.write(
            self.style.SUCCESS("DONE seeding realistic orders.")
        )
        
          
#Cách dùng: python manage.py seed_orders --total-orders 10
# Xóa dữ liệu: python manage.py shell ->
# from shops.models import Order
# Order.objects.all().delete()
