import json
from datetime import timedelta
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.contrib.messages import get_messages
from django.utils import timezone

from shops.models import AfterSalesRequest, Category, Coupon, Order, OrderItem, OrderStatusLog, Product, UserNotification
from shops.utils.order_expiry import expire_stale_pending_orders
from shops.views import _apply_status_change
from users.models import Profile, RefundWalletTransaction


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
                "full_name": "Buyer Test",
                "email": "buyer@example.com",
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

    @patch("shops.views.calculate_shipping_cost", return_value=(0, None))
    @patch("shops.views._send_order_email", return_value=None)
    def test_guest_checkout_can_create_order_without_login(self, _mock_email, _mock_shipping):
        product = Product.objects.create(
            name="Phone Guest",
            slug="phone-guest",
            price=3500000,
            image="https://example.com/guest.jpg",
            stock=4,
            reserved_stock=0,
            available=True,
        )

        session = self.client.session
        session["cart"] = {
            str(product.id): {
                "quantity": 1,
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
                "full_name": "Guest Buyer",
                "email": "guest@example.com",
                "phone": "0911111111",
                "address": "123 Guest Street",
                "payment_method": "COD",
            },
        )

        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(guest_email="guest@example.com")
        product.refresh_from_db()
        self.assertIsNone(order.user)
        self.assertEqual(order.guest_name, "Guest Buyer")
        self.assertEqual(order.phone, "0911111111")
        self.assertEqual(product.reserved_stock, 1)

    def test_guest_cannot_apply_coupon(self):
        now = timezone.now()
        coupon = Coupon.objects.create(
            code="GUEST10",
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=1),
            discount=10,
            used_count=0,
            usage_limit=0,
            active=True,
        )

        session = self.client.session
        session["coupon_id"] = coupon.id
        session.save()

        response = self.client.post(
            reverse("shops:apply_coupon"),
            {"code": coupon.code},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("coupon_id", self.client.session)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("Vui lòng đăng nhập để sử dụng voucher.", messages)

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

    def test_apply_status_change_creates_user_notification(self):
        order, _product = self._create_order_with_item(
            payment_method="COD",
            paid=False,
            qty=1,
            stock=5,
            reserved_stock=1,
        )

        ok, error = _apply_status_change(order, "Processing", source="test")

        self.assertTrue(ok, error)
        notification = UserNotification.objects.get(user=self.user, notification_type=UserNotification.TYPE_ORDER_STATUS)
        self.assertIn(f"Đơn hàng #{order.id}", notification.title)
        self.assertIn("Pending", notification.message)
        self.assertIn("Processing", notification.message)

    def test_user_cancel_order_requires_reason(self):
        self.client.force_login(self.user)
        order, product = self._create_order_with_item(
            payment_method="COD",
            paid=False,
            qty=1,
            stock=5,
            reserved_stock=1,
        )

        response = self.client.post(
            reverse("shops:cancel_order", args=[order.id]),
            {"cancel_reason": ""},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(order.status, "Pending")
        self.assertEqual(order.cancel_reason, "")
        self.assertEqual(product.reserved_stock, 1)

    def test_user_cancel_order_saves_reason(self):
        self.client.force_login(self.user)
        order, product = self._create_order_with_item(
            payment_method="COD",
            paid=False,
            qty=1,
            stock=5,
            reserved_stock=1,
        )

        response = self.client.post(
            reverse("shops:cancel_order", args=[order.id]),
            {"cancel_reason": "Đổi địa chỉ nhận hàng"},
        )

        self.assertRedirects(response, reverse("shops:order_history"))
        order.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(order.status, "Cancelled")
        self.assertEqual(order.cancel_reason, "Đổi địa chỉ nhận hàng")
        self.assertEqual(product.reserved_stock, 0)


class AfterSalesNotificationTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            username="buyer_aftersales",
            password="pass12345",
            email="buyer_aftersales@example.com",
        )
        self.staff = self.user_model.objects.create_user(
            username="staff_aftersales",
            password="pass12345",
            email="staff_aftersales@example.com",
            is_staff=True,
        )
        Profile.objects.create(user=self.user, phone="0900000001", address="HCM")
        Profile.objects.create(user=self.staff, phone="0900000002", address="HCM")
        self.order = Order.objects.create(
            user=self.user,
            address="HCM",
            phone="0900000001",
            total_price=100000,
            status="Delivered",
            payment_method="COD",
            paid=True,
        )

    def _create_order_with_item(
        self,
        *,
        status="Pending",
        payment_method="COD",
        paid=False,
        qty=1,
        stock=5,
        reserved_stock=0,
        coupon=None,
        created_at=None,
    ):
        product = Product.objects.create(
            name=f"AfterSales-{uuid.uuid4().hex[:8]}",
            slug=f"after-sales-{uuid.uuid4().hex[:10]}",
            price=100000,
            image="https://example.com/p.jpg",
            stock=stock,
            reserved_stock=reserved_stock,
            available=True,
        )
        order = Order.objects.create(
            user=self.user,
            address="HCM",
            phone="0900000001",
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

    def test_create_after_sales_request_notifies_staff(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("shops:create_after_sales_request", args=[self.order.id]),
            {
                "request_type": AfterSalesRequest.TYPE_RETURN,
                "reason": "Sản phẩm bị lỗi",
                "contact_name": "Buyer",
                "contact_email": "buyer_aftersales@example.com",
                "contact_phone": "0900000001",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            UserNotification.objects.filter(
                user=self.staff,
                notification_type=UserNotification.TYPE_AFTER_SALES,
            ).exists()
        )

    def test_update_after_sales_request_notifies_customer(self):
        record = AfterSalesRequest.objects.create(
            order=self.order,
            request_type=AfterSalesRequest.TYPE_RETURN,
            reason="Sản phẩm bị lỗi",
            requested_by=self.user,
            contact_name="Buyer",
        )
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("shops:update_after_sales_request", args=[record.id]),
            {
                "status": AfterSalesRequest.STATUS_APPROVED,
                "refund_amount": 100000,
                "resolution_note": "Đã duyệt hoàn trả",
            },
        )

        self.assertEqual(response.status_code, 302)
        notification = UserNotification.objects.filter(
            user=self.user,
            notification_type=UserNotification.TYPE_AFTER_SALES,
        ).latest("created_at")
        self.assertIn("đã được cập nhật", notification.title)
        self.assertIn("Đã duyệt", notification.message)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.refund_wallet_balance, 100000)
        self.assertTrue(
            RefundWalletTransaction.objects.filter(
                user=self.user,
                after_sales_request=record,
                transaction_type=RefundWalletTransaction.TYPE_REFUND,
            ).exists()
        )

    def test_approved_refund_is_only_credited_once(self):
        record = AfterSalesRequest.objects.create(
            order=self.order,
            request_type=AfterSalesRequest.TYPE_REFUND,
            reason="Xin hoàn tiền",
            requested_by=self.user,
            refund_amount=120000,
            contact_name="Buyer",
        )
        self.client.force_login(self.staff)

        first = self.client.post(
            reverse("shops:update_after_sales_request", args=[record.id]),
            {
                "status": AfterSalesRequest.STATUS_APPROVED,
                "refund_amount": 120000,
                "resolution_note": "Duyệt lần 1",
            },
        )
        second = self.client.post(
            reverse("shops:update_after_sales_request", args=[record.id]),
            {
                "status": AfterSalesRequest.STATUS_APPROVED,
                "refund_amount": 120000,
                "resolution_note": "Duyệt lại",
            },
        )

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.refund_wallet_balance, 120000)
        self.assertEqual(
            RefundWalletTransaction.objects.filter(after_sales_request=record).count(),
            1,
        )

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

    def test_order_detail_is_accessible_from_order_history_for_owner(self):
        self.client.force_login(self.user)
        order, _product = self._create_order_with_item(status="Pending")

        history_response = self.client.get(reverse("shops:order_history"))
        self.assertEqual(history_response.status_code, 200)
        self.assertContains(history_response, reverse("shops:order_detail", args=[order.id]))

        detail_response = self.client.get(reverse("shops:order_detail", args=[order.id]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, f"Đơn hàng #{order.id}")

    def test_user_can_create_after_sales_request_for_delivered_order(self):
        self.client.force_login(self.user)
        order, _product = self._create_order_with_item(status="Delivered", paid=True)

        response = self.client.post(
            reverse("shops:create_after_sales_request", args=[order.id]),
            {
                "request_type": AfterSalesRequest.TYPE_RETURN,
                "reason": "San pham bi loi",
                "contact_name": "Buyer",
                "contact_email": "buyer@example.com",
                "contact_phone": "0900000000",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        req = AfterSalesRequest.objects.get(order=order)
        self.assertEqual(req.request_type, AfterSalesRequest.TYPE_RETURN)
        self.assertEqual(req.status, AfterSalesRequest.STATUS_PENDING)

    def test_user_cannot_create_after_sales_request_for_pending_order(self):
        self.client.force_login(self.user)
        order, _product = self._create_order_with_item(status="Pending", paid=False)

        response = self.client.post(
            reverse("shops:create_after_sales_request", args=[order.id]),
            {
                "request_type": AfterSalesRequest.TYPE_REFUND,
                "reason": "Muon hoan tien",
                "contact_name": "Buyer",
                "contact_email": "buyer@example.com",
                "contact_phone": "0900000000",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AfterSalesRequest.objects.filter(order=order).exists())

    def test_order_xml_export_contains_after_sales_requests(self):
        self.client.force_login(self.user)
        order, _product = self._create_order_with_item(status="Delivered", paid=True)
        AfterSalesRequest.objects.create(
            order=order,
            request_type=AfterSalesRequest.TYPE_REFUND,
            status=AfterSalesRequest.STATUS_APPROVED,
            reason="Hoan tien don nay",
            requested_by=self.user,
            contact_name="Buyer",
            contact_email="buyer@example.com",
            contact_phone="0900000000",
            refund_amount=100000,
        )

        response = self.client.get(reverse("shops:order_xml_export", args=[order.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml; charset=utf-8")
        self.assertIn(b"<after_sales_requests>", response.content)
        self.assertIn(b"<type>REFUND</type>", response.content)


class CategoryVisibilityTests(TestCase):
    def setUp(self):
        self.active_category = Category.objects.create(name="Phones", slug="phones", is_active=True)
        self.hidden_category = Category.objects.create(name="Hidden", slug="hidden", is_active=False)
        self.visible_product = Product.objects.create(
            name="Visible Phone",
            slug="visible-phone",
            price=100000,
            image="https://example.com/visible.jpg",
            stock=5,
            available=True,
            category=self.active_category,
        )
        self.hidden_product = Product.objects.create(
            name="Hidden Phone",
            slug="hidden-phone",
            price=100000,
            image="https://example.com/hidden.jpg",
            stock=5,
            available=True,
            category=self.hidden_category,
        )
        self.admin = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="pass12345",
        )

    def test_product_page_hides_products_from_disabled_categories(self):
        response = self.client.get(reverse("shops:product"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.visible_product.name)
        self.assertNotContains(response, self.hidden_product.name)
        self.assertContains(response, self.active_category.name)
        self.assertNotContains(response, self.hidden_category.name)

    def test_product_detail_returns_404_for_disabled_category_product(self):
        response = self.client.get(reverse("shops:detail", args=[self.hidden_product.slug]))

        self.assertEqual(response.status_code, 404)

    def test_category_toggle_switches_visibility(self):
        self.client.force_login(self.admin)

        response = self.client.post(reverse("shops:category_toggle", args=[self.hidden_category.id]))

        self.assertRedirects(response, reverse("shops:category_manage"))
        self.hidden_category.refresh_from_db()
        self.assertTrue(self.hidden_category.is_active)


class CartUpdateStockValidationTests(TestCase):
    def test_update_cart_ajax_returns_updated_totals(self):
        product = Product.objects.create(
            name="Phone Ajax",
            slug="phone-ajax",
            price=2500000,
            image="https://example.com/ajax.jpg",
            stock=5,
            reserved_stock=0,
            available=True,
        )

        session = self.client.session
        session["cart"] = {
            str(product.id): {
                "quantity": 1,
                "price": product.price,
                "name": product.name,
                "image": product.image,
            }
        }
        session.save()

        response = self.client.post(
            reverse("shops:update_cart", args=[product.id]),
            {"quantity": 2},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["quantity"], 2)
        self.assertEqual(payload["item_total"], product.price * 2)
        self.assertEqual(payload["total_price"], product.price * 2)
        self.assertEqual(self.client.session["cart"][str(product.id)]["quantity"], 2)

    def test_update_cart_rejects_quantity_greater_than_available_stock(self):
        product = Product.objects.create(
            name="Phone Y",
            slug="phone-y",
            price=3000000,
            image="https://example.com/y.jpg",
            stock=3,
            reserved_stock=1,
            available=True,
        )

        session = self.client.session
        session["cart"] = {
            str(product.id): {
                "quantity": 1,
                "price": product.price,
                "name": product.name,
                "image": product.image,
            }
        }
        session.save()

        response = self.client.post(
            reverse("shops:update_cart", args=[product.id]),
            {"quantity": 3},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session["cart"][str(product.id)]["quantity"], 1)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("Phone Y chỉ còn 2 sản phẩm.", messages)

    def test_checkout_redirects_to_cart_when_cart_quantity_exceeds_stock(self):
        user = get_user_model().objects.create_user(
            username="checkout_buyer",
            password="pass12345",
            email="checkout@example.com",
        )
        Profile.objects.create(user=user, phone="0900000001", address="HCM")
        self.client.force_login(user)

        product = Product.objects.create(
            name="Phone Z",
            slug="phone-z",
            price=4000000,
            image="https://example.com/z.jpg",
            stock=2,
            reserved_stock=1,
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

        response = self.client.get(reverse("shops:checkout"), follow=True)

        self.assertRedirects(response, reverse("shops:cart_detail"))
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("Phone Z chỉ còn 1 sản phẩm.", messages)


class AiChatbotOrderTrackingTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            username="chatbuyer",
            password="pass12345",
            email="chatbuyer@example.com",
        )
        Profile.objects.create(user=self.user, phone="0900000002", address="HCM")
        self.client.force_login(self.user)

        self.product = Product.objects.create(
            name="Chatbot Phone",
            slug="chatbot-phone",
            price=3000000,
            image="https://example.com/chatbot-phone.jpg",
            stock=10,
            reserved_stock=0,
            available=True,
        )
        self.order = Order.objects.create(
            user=self.user,
            address="HCM",
            phone="0900000002",
            total_price=self.product.price,
            status="Shipped",
            payment_method="COD",
            tracking_code="ABC123",
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            price=self.product.price,
            quantity=1,
        )
        OrderStatusLog.objects.create(
            order=self.order,
            from_status="Processing",
            to_status="Shipped",
            source="test",
        )

    @patch("shops.ai.chatbot.ask_gemini")
    def test_chatbot_prompts_for_order_code_before_lookup(self, mock_ask_gemini):
        response = self.client.post(
            reverse("shops:ai_chat"),
            data=json.dumps({"message": "Đơn hàng của tôi đâu?"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["reply"], "Bạn hãy nhập mã đơn hàng.")
        self.assertEqual(
            self.client.session.get("ai_chatbot_state", {}).get("awaiting_order_code"),
            True,
        )
        mock_ask_gemini.assert_not_called()

    @patch("shops.ai.chatbot.ask_gemini")
    def test_chatbot_returns_order_status_after_receiving_code(self, mock_ask_gemini):
        session = self.client.session
        session["ai_chatbot_state"] = {"awaiting_order_code": True}
        session.save()

        response = self.client.post(
            reverse("shops:ai_chat"),
            data=json.dumps({"message": "ABC123"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("Đơn hàng #", payload["reply"])
        self.assertIn("Đang giao", payload["reply"])
        self.assertNotIn("ai_chatbot_state", self.client.session)
        mock_ask_gemini.assert_not_called()


class ShopStatsViewTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.staff = self.user_model.objects.create_user(
            username="staffstats",
            password="pass12345",
            email="staff@example.com",
            is_staff=True,
        )
        self.customer = self.user_model.objects.create_user(
            username="memberstats",
            password="pass12345",
            email="member@example.com",
        )
        self.category = Category.objects.create(name="Phone Stats", slug="phone-stats")

    def test_shop_stats_includes_sales_inventory_and_customer_segments(self):
        hot = Product.objects.create(
            name="Hot Product",
            slug="hot-product",
            price=100000,
            image="https://example.com/hot.jpg",
            stock=20,
            reserved_stock=3,
            available=True,
            category=self.category,
        )
        slow = Product.objects.create(
            name="Slow Product",
            slug="slow-product",
            price=50000,
            image="https://example.com/slow.jpg",
            stock=8,
            reserved_stock=1,
            available=True,
            category=self.category,
        )
        guest_only = Product.objects.create(
            name="Guest Product",
            slug="guest-product",
            price=70000,
            image="https://example.com/guest.jpg",
            stock=50,
            reserved_stock=0,
            available=True,
            category=self.category,
        )

        logged_order = Order.objects.create(
            user=self.customer,
            address="HCM",
            phone="0900000000",
            total_price=250000,
            status="Delivered",
            paid=True,
        )
        OrderItem.objects.create(order=logged_order, product=hot, price=100000, quantity=2)
        OrderItem.objects.create(order=logged_order, product=slow, price=50000, quantity=1)

        guest_order = Order.objects.create(
            guest_name="Guest Buyer",
            guest_email="guest@example.com",
            address="HN",
            phone="0911111111",
            total_price=210000,
            status="Delivered",
            paid=True,
        )
        OrderItem.objects.create(order=guest_order, product=guest_only, price=70000, quantity=3)

        self.client.force_login(self.staff)
        response = self.client.get(reverse("shops:shop_stats"))

        self.assertEqual(response.status_code, 200)

        best_products = list(response.context["best_selling_products"])
        least_products = list(response.context["least_selling_products"])
        inventory_products = list(response.context["inventory_products"])
        customer_stats = response.context["customer_purchase_stats"]

        self.assertEqual(best_products[0].name, "Guest Product")
        self.assertEqual(best_products[0].sold_qty, 3)
        self.assertEqual(least_products[0].name, "Slow Product")
        self.assertEqual(least_products[0].sold_qty, 1)
        self.assertEqual(response.context["low_stock_count"], 1)
        self.assertEqual(response.context["low_stock_products"][0].name, "Slow Product")

        inventory_map = {product.name: product.available_stock_count for product in inventory_products}
        self.assertEqual(inventory_map["Hot Product"], 17)
        self.assertEqual(inventory_map["Slow Product"], 7)

        self.assertEqual(customer_stats[0]["label"], "Khách đã đăng nhập")
        self.assertEqual(customer_stats[0]["order_count"], 1)
        self.assertEqual(customer_stats[0]["total_items"], 3)
        self.assertEqual(customer_stats[0]["revenue"], 250000)
        self.assertEqual(customer_stats[0]["avg_order_value"], 250000)

        self.assertEqual(customer_stats[1]["label"], "Khách không đăng nhập")
        self.assertEqual(customer_stats[1]["order_count"], 1)
        self.assertEqual(customer_stats[1]["total_items"], 3)
        self.assertEqual(customer_stats[1]["revenue"], 210000)
        self.assertEqual(customer_stats[1]["avg_order_value"], 210000)
