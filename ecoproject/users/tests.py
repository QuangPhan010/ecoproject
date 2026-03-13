from unittest.mock import patch
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.test.utils import override_settings
from django.utils import timezone
from django.contrib.auth.hashers import check_password, make_password

from .models import MysteryBoxRewardOption, Profile, RewardVoucherOption
from .views import MYSTERY_BOX_PITY_RULES, PASSWORD_RESET_OTP_RESEND_SECONDS
from .models import PasswordResetOTP
from shops.models import Coupon, CouponUsage


class RewardAdminConsoleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="member", password="pass123")
        self.admin_user = User.objects.create_user(
            username="staff",
            password="pass123",
            is_staff=True,
        )
        Profile.objects.create(user=self.user)
        Profile.objects.create(user=self.admin_user)
        self.voucher = RewardVoucherOption.objects.create(
            name="Voucher 10%",
            cost_points=100,
            discount=10,
            max_discount=50000,
            valid_days=7,
            active=True,
        )
        self.reward = MysteryBoxRewardOption.objects.create(
            name="+50 diem",
            box_tier="STANDARD",
            reward_type="POINTS",
            points_value=50,
            weight=10,
            active=True,
        )

    def test_user_reward_page_does_not_render_admin_forms(self):
        self.client.login(username="staff", password="pass123")

        response = self.client.get(reverse("users:rewards"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Quản lý gói voucher đổi điểm (Admin)")
        self.assertNotContains(response, reverse("users:manage_voucher_options"))

    def test_user_minigame_page_does_not_render_admin_forms(self):
        self.client.login(username="staff", password="pass123")

        response = self.client.get(reverse("users:minigame"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Quản lý quà Mystery Box (Admin)")
        self.assertNotContains(response, reverse("users:manage_mystery_rewards"))

    def test_reward_admin_console_requires_staff(self):
        self.client.login(username="member", password="pass123")

        response = self.client.get(reverse("users:reward_admin_console"))

        self.assertEqual(response.status_code, 403)

    def test_reward_admin_console_renders_management_sections_for_staff(self):
        self.client.login(username="staff", password="pass123")

        response = self.client.get(reverse("users:reward_admin_console"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reward Admin Console")
        self.assertContains(response, self.voucher.name)
        self.assertContains(response, self.reward.name)

    def test_manage_voucher_redirects_back_to_admin_console(self):
        self.client.login(username="staff", password="pass123")

        response = self.client.post(
            reverse("users:manage_voucher_options"),
            {
                "action": "update",
                "option_id": self.voucher.id,
                "name": "Voucher 15%",
                "cost_points": 150,
                "discount": 15,
                "max_discount": 70000,
                "valid_days": 10,
                "sort_order": 2,
                "active": "on",
            },
        )

        self.assertRedirects(response, reverse("users:reward_admin_console"))

    def test_manage_mystery_rewards_redirects_back_to_admin_console(self):
        self.client.login(username="staff", password="pass123")

        response = self.client.post(
            reverse("users:manage_mystery_rewards"),
            {
                "action": "update",
                "reward_id": self.reward.id,
                "selected_box_type": "standard",
                "name": "+100 diem",
                "box_tier": "STANDARD",
                "reward_type": "POINTS",
                "points_value": 100,
                "plays_value": 0,
                "voucher_discount": 0,
                "voucher_max_discount": 0,
                "voucher_valid_days": 0,
                "weight": 20,
                "sort_order": 1,
                "active": "on",
            },
        )

        self.assertRedirects(response, f"{reverse('users:reward_admin_console')}?box=standard")

    def test_navbar_voucher_bag_shows_only_owned_active_unused_vouchers(self):
        self.client.login(username="member", password="pass123")
        now = timezone.now()

        active_coupon = Coupon.objects.create(
            owner=self.user,
            code="MEMBER10",
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=3),
            discount=10,
            max_discount=50000,
            active=True,
        )
        expired_coupon = Coupon.objects.create(
            owner=self.user,
            code="OLD10",
            valid_from=now - timedelta(days=3),
            valid_to=now - timedelta(hours=1),
            discount=10,
            max_discount=30000,
            active=False,
        )
        used_coupon = Coupon.objects.create(
            owner=self.user,
            code="USED10",
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=2),
            discount=10,
            max_discount=40000,
            active=True,
        )
        CouponUsage.objects.create(coupon=used_coupon, user=self.user)
        Coupon.objects.create(
            owner=self.admin_user,
            code="STAFF10",
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=2),
            discount=10,
            max_discount=40000,
            active=True,
        )

        response = self.client.get(reverse("users:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Túi Voucher")
        self.assertContains(response, active_coupon.code)
        self.assertNotContains(response, expired_coupon.code)
        self.assertNotContains(response, used_coupon.code)
        self.assertNotContains(response, "STAFF10")


class MysteryBoxExperienceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="player", password="pass123")
        self.profile = Profile.objects.create(user=self.user, minigame_plays=20)
        MysteryBoxRewardOption.objects.create(
            name="+50 diem",
            box_tier="STANDARD",
            reward_type="POINTS",
            points_value=50,
            weight=30,
            active=True,
            sort_order=1,
        )
        MysteryBoxRewardOption.objects.create(
            name="+1 luot",
            box_tier="STANDARD",
            reward_type="PLAYS",
            plays_value=1,
            weight=20,
            active=True,
            sort_order=2,
        )
        self.standard_voucher = MysteryBoxRewardOption.objects.create(
            name="Voucher 5%",
            box_tier="STANDARD",
            reward_type="VOUCHER",
            voucher_discount=5,
            voucher_max_discount=30000,
            voucher_valid_days=5,
            weight=10,
            active=True,
            sort_order=3,
        )
        MysteryBoxRewardOption.objects.create(
            name="Chuc ban may man lan sau",
            box_tier="STANDARD",
            reward_type="EMPTY",
            weight=40,
            active=True,
            sort_order=4,
        )

    def test_minigame_page_shows_grouped_odds_and_pity_status(self):
        self.client.login(username="player", password="pass123")

        response = self.client.get(reverse("users:minigame"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tỷ lệ theo cấu hình hiện tại")
        self.assertContains(response, "Voucher Pity System")
        odds = response.context["reward_odds"]
        self.assertEqual([item["type"] for item in odds], ["POINTS", "PLAYS", "VOUCHER", "EMPTY"])
        self.assertGreater(sum(item["weight"] for item in odds), 0)
        self.assertAlmostEqual(sum(item["percent"] for item in odds), 100.0, places=1)
        self.assertEqual(response.context["pity_status"]["threshold"], MYSTERY_BOX_PITY_RULES["standard"]["threshold"])

    @patch("users.views.random.choices", side_effect=lambda population, weights=None, k=1: [population[0]])
    def test_open_mystery_box_increments_standard_pity_after_no_voucher(self, _mock_choices):
        self.client.login(username="player", password="pass123")

        response = self.client.post(
            reverse("users:open_mystery_box"),
            {
                "open_count": 1,
                "box_type": "standard",
                "clicked_index": 0,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.standard_voucher_pity, 1)
        self.assertFalse(response.json()["pity_triggered"])

    @patch("users.views.random.choices", side_effect=lambda population, weights=None, k=1: [population[0]])
    def test_open_mystery_box_guarantees_voucher_when_pity_reaches_threshold(self, _mock_choices):
        self.client.login(username="player", password="pass123")
        self.profile.standard_voucher_pity = MYSTERY_BOX_PITY_RULES["standard"]["threshold"] - 1
        self.profile.save(update_fields=["standard_voucher_pity"])

        response = self.client.post(
            reverse("users:open_mystery_box"),
            {
                "open_count": 1,
                "box_type": "standard",
                "clicked_index": 0,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.profile.refresh_from_db()
        self.assertTrue(payload["pity_triggered"])
        self.assertEqual(self.profile.standard_voucher_pity, 0)
        self.assertEqual(payload["rewards"][0]["type"], "VOUCHER")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetOTPTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="otpuser",
            email="otp@example.com",
            password="oldpass123",
        )
        Profile.objects.create(user=self.user)

    def test_password_reset_request_sends_otp_email(self):
        response = self.client.post(
            reverse("users:password_reset"),
            {"email": "otp@example.com"},
        )

        self.assertRedirects(response, f"{reverse('users:password_reset_verify')}?email=otp%40example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Ma OTP", mail.outbox[0].subject)
        otp = PasswordResetOTP.objects.get(user=self.user, used=False)
        raw_code = mail.outbox[0].body.split("la: ", 1)[1].splitlines()[0].strip()
        self.assertNotEqual(otp.code, raw_code)
        self.assertTrue(check_password(raw_code, otp.code))

    def test_password_reset_verify_accepts_valid_otp(self):
        otp = PasswordResetOTP.objects.create(
            user=self.user,
            email=self.user.email,
            code=make_password("123456"),
            expires_at=PasswordResetOTP.build_expiry(),
        )

        response = self.client.post(
            reverse("users:password_reset_verify"),
            {"email": self.user.email, "otp": "123456"},
        )

        self.assertRedirects(response, reverse("users:password_reset_confirm"))
        self.assertEqual(self.client.session["password_reset_verified_otp_id"], otp.id)

    def test_password_reset_confirm_updates_password_after_verified_otp(self):
        otp = PasswordResetOTP.objects.create(
            user=self.user,
            email=self.user.email,
            code=make_password("123456"),
            expires_at=PasswordResetOTP.build_expiry(),
        )
        session = self.client.session
        session["password_reset_verified_otp_id"] = otp.id
        session.save()

        response = self.client.post(
            reverse("users:password_reset_confirm"),
            {
                "new_password1": "NewStrongPass123!",
                "new_password2": "NewStrongPass123!",
            },
        )

        self.assertRedirects(response, reverse("users:password_reset_complete"))
        otp.refresh_from_db()
        self.assertTrue(otp.used)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewStrongPass123!"))

    def test_password_reset_verify_rejects_invalid_otp(self):
        otp = PasswordResetOTP.objects.create(
            user=self.user,
            email=self.user.email,
            code=make_password("123456"),
            expires_at=PasswordResetOTP.build_expiry(),
        )

        response = self.client.post(
            reverse("users:password_reset_verify"),
            {"email": self.user.email, "otp": "000000"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        otp.refresh_from_db()
        self.assertEqual(otp.attempts, 1)
        self.assertContains(response, "OTP không hợp lệ.")

    def test_password_reset_confirm_rejects_expired_otp_session(self):
        otp = PasswordResetOTP.objects.create(
            user=self.user,
            email=self.user.email,
            code=make_password("123456"),
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        session = self.client.session
        session["password_reset_verified_otp_id"] = otp.id
        session.save()

        response = self.client.get(reverse("users:password_reset_confirm"), follow=True)

        self.assertRedirects(response, reverse("users:password_reset"))
        otp.refresh_from_db()
        self.assertTrue(otp.used)

    def test_password_reset_resend_is_rate_limited_for_60_seconds(self):
        PasswordResetOTP.objects.create(
            user=self.user,
            email=self.user.email,
            code=make_password("123456"),
            expires_at=PasswordResetOTP.build_expiry(),
        )

        response = self.client.post(
            reverse("users:password_reset_resend"),
            {"email": self.user.email},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vui lòng chờ")
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_resend_sends_new_otp_after_cooldown(self):
        otp = PasswordResetOTP.objects.create(
            user=self.user,
            email=self.user.email,
            code=make_password("123456"),
            expires_at=PasswordResetOTP.build_expiry(),
        )
        otp.created_at = timezone.now() - timedelta(seconds=PASSWORD_RESET_OTP_RESEND_SECONDS + 1)
        otp.save(update_fields=["created_at"])

        response = self.client.post(
            reverse("users:password_reset_resend"),
            {"email": self.user.email},
        )

        self.assertRedirects(response, f"{reverse('users:password_reset_verify')}?email=otp%40example.com")
        self.assertEqual(len(mail.outbox), 1)
        otp.refresh_from_db()
        self.assertTrue(otp.used)
        self.assertEqual(PasswordResetOTP.objects.filter(user=self.user, used=False).count(), 1)
