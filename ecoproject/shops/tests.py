from datetime import timedelta
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from shops.models import Coupon, Order, OrderItem, OrderStatusLog, Product
from shops.utils.order_expiry import expire_stale_pending_orders
from shops.views import _apply_status_change
from users.models import Profile


class OrderStockLifecycleTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            username="buyer",
            password="pass12345",
            email="buyer@example.com",
        )
        Profile.objects.create(user=self.user, phone="0900000000", address="HCM")

    def _create_order_with_item(
        self,
        *,
        status="Pending",
        payment_method="COD",
        paid=False,
        qty=2,
        stock=10,
        reserved_stock=0,
        coupon=None,
        created_at=None,
    ):
        product = Product.objects.create(
            name=f"Product-{uuid.uuid4().hex[:8]}",
            slug=f"product-{uuid.uuid4().hex[:10]}",
            price=100000,
            image="https://example.com/p.jpg",
            stock=stock,
            reserved_stock=reserved_stock,
            available=True,
        )
        order = Order.objects.create(
            user=self.user,
            address="HCM",
            phone="0900000000",
            total_price=qty * product.price,
            status=status,
            payment_method=payment_method,
            paid=paid,
            coupon=coupon,
        )
        if created_at is not None:
            Order.objects.filter(id=order.id).update(created_at=created_at)
            order.refresh_from_db()
        OrderItem.objects.create(order=order, product=product, price=product.price, quantity=qty)
        return order, product

    @patch("shops.views.calculate_shipping_cost", return_value=(0, None))
    @patch("shops.views._send_order_email", return_value=None)
    def test_checkout_place_order_reserves_stock(self, _mock_email, _mock_shipping):
        self.client.force_login(self.user)
        product = Product.objects.create(
            name="Phone X",
            slug="phone-x",
            price=5000000,
            image="https://example.com/x.jpg",
            stock=5,
            reserved_stock=0,
            available=True,
        )

        session = self.client.session
        session["cart"] = {
            str(product.id): {
                "quantity": 2,
                "price": product.price,
                "name": product.name,
                "image": product.image,
            }
        }
        session.save()

        response = self.client.post(
            reverse("shops:checkout"),
            data={
                "action": "place_order",
                "phone": "0900000000",
                "address": "HCM",
                "payment_method": "COD",
            },
        )
        self.assertEqual(response.status_code, 302)

        order = Order.objects.get(user=self.user)
        product.refresh_from_db()
        self.assertEqual(order.status, "Pending")
        self.assertFalse(order.paid)
        self.assertEqual(product.stock, 5)
        self.assertEqual(product.reserved_stock, 2)

    def test_bank_processing_finalizes_stock_and_coupon_usage(self):
        now = timezone.now()
        coupon = Coupon.objects.create(
            code="TEST10",
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=1),
            discount=10,
            used_count=0,
            usage_limit=0,
            active=True,
        )
        order, product = self._create_order_with_item(
            payment_method="BANK",
            paid=False,
            qty=2,
            stock=5,
            reserved_stock=2,
            coupon=coupon,
        )

        ok, error = _apply_status_change(order, "Processing", source="test")
        self.assertTrue(ok, error)

        order.refresh_from_db()
        product.refresh_from_db()
        coupon.refresh_from_db()

        self.assertEqual(order.status, "Processing")
        self.assertTrue(order.paid)
        self.assertEqual(product.stock, 3)
        self.assertEqual(product.reserved_stock, 0)
        self.assertEqual(product.sold, 2)
        self.assertEqual(coupon.used_count, 1)

    def test_cancel_releases_reserved_stock_for_unpaid_order(self):
        order, product = self._create_order_with_item(
            payment_method="COD",
            paid=False,
            qty=2,
            stock=8,
            reserved_stock=2,
        )

        ok, error = _apply_status_change(order, "Cancelled", source="test")
        self.assertTrue(ok, error)

        order.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(order.status, "Cancelled")
        self.assertFalse(order.paid)
        self.assertEqual(product.stock, 8)
        self.assertEqual(product.reserved_stock, 0)

    def test_invalid_transition_is_blocked(self):
        order, _product = self._create_order_with_item(status="Pending")

        ok, error = _apply_status_change(order, "Delivered", source="test")
        self.assertFalse(ok)
        self.assertIn("Không thể chuyển trạng thái", error)
        order.refresh_from_db()
        self.assertEqual(order.status, "Pending")

    def test_expire_stale_orders_releases_stock_and_logs(self):
        stale_time = timezone.now() - timedelta(hours=4)
        order, product = self._create_order_with_item(
            status="Pending",
            payment_method="COD",
            paid=False,
            qty=1,
            stock=4,
            reserved_stock=1,
            created_at=stale_time,
        )

        expired = expire_stale_pending_orders(expire_hours=3, batch_size=50)
        self.assertEqual(expired, 1)

        order.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(order.status, "Cancelled")
        self.assertEqual(product.reserved_stock, 0)
        self.assertTrue(
            OrderStatusLog.objects.filter(
                order=order,
                from_status="Pending",
                to_status="Cancelled",
                source="auto_expire",
            ).exists()
        )
