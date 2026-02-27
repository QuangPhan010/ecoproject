import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from shops.models import Order, OrderItem, Product
from shops.rank_utils import update_user_rank_realtime  # 🔥 thêm dòng này


class Command(BaseCommand):
    help = "Create random orders and update user rank realtime."

    def add_arguments(self, parser):
        parser.add_argument(
            "--total-orders",
            type=int,
            default=100,
            help="Total number of orders to create.",
        )

    def handle(self, *args, **options):

        total_orders = options["total_orders"]

        users = list(get_user_model().objects.all())
        products = list(Product.objects.filter(available=True))

        if not users or not products:
            self.stdout.write(self.style.ERROR("Missing users or products."))
            return

        status_choices = [s for s, _ in Order.STATUS_CHOICES]
        payment_choices = [p for p, _ in Order.PAYMENT_CHOICES]

        now = timezone.now()

        created = 0
        day_offset = 0

        while created < total_orders:

            # mỗi ngày 6–8 đơn
            orders_today = random.randint(6, 8)

            base_date = now - timedelta(days=day_offset)

            seconds_step = 86400 // orders_today

            for i in range(orders_today):

                if created >= total_orders:
                    break

                user = random.choice(users)

                created_at = base_date.replace(
                    hour=0, minute=0, second=0, microsecond=0
                ) + timedelta(
                    seconds=i * seconds_step + random.randint(0, seconds_step - 1)
                )

                with transaction.atomic():

                    picked = random.sample(
                        products,
                        random.randint(1, min(4, len(products)))
                    )

                    total_price = 0
                    item_data = []

                    for p in picked:
                        qty = random.randint(1, 3)
                        total_price += p.price * qty
                        item_data.append((p, qty))

                    status = random.choice(status_choices)

                    order = Order.objects.create(
                        user=user,
                        address="Địa chỉ test",
                        phone="0900000000",
                        total_price=total_price,
                        shipping_method="Standard",
                        shipping_cost=0,
                        discount=0,
                        payment_method=random.choice(payment_choices),

                        # 🔥 quan trọng để tính rank
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

                    # 🔥 UPDATE RANK REALTIME
                    update_user_rank_realtime(user)

                created += 1

            day_offset += 1

            self.stdout.write(
                self.style.SUCCESS(f"Created {created} orders...")
            )

        self.stdout.write(
            self.style.SUCCESS("DONE. All ranks updated.")
        )



#Cách dùng: python manage.py seed_orders --total-orders 10
# Xóa dữ liệu: python manage.py shell ->
# from shops.models import Order
# Order.objects.all().delete()