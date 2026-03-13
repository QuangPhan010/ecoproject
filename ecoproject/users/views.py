from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from .forms import (
    LoginForm,
    UserRegistrationForm,
    UserEditForm,
    ProfileEditForm,
    PasswordResetOTPRequestForm,
    PasswordResetOTPVerifyForm,
    PasswordResetOTPSetPasswordForm,
)
from .models import (
    Profile,
    PointExchange,
    MysteryBoxHistory,
    RewardVoucherOption,
    MysteryBoxRewardOption,
    PasswordResetOTP,
)
from django.contrib import messages
from django.contrib.auth.models import Group, User
from shops.models import Order, Coupon
from django.db.models import Sum
from django.contrib.auth.decorators import login_required
from shops.rank_utils import update_user_rank_realtime
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from datetime import timedelta
import uuid
import random

PREMIUM_BOX_ALLOWED_RANKS = {
    Profile.RANK_GOLD,
    Profile.RANK_PLATINUM,
    Profile.RANK_DIAMOND,
    Profile.RANK_ELITE,
    Profile.RANK_LEGEND,
}

MINIGAME_OPTIONS = [
    {"key": "G1", "label": "Mystery Box x1", "cost": 100, "plays": 1},
    {"key": "G5", "label": "Mystery Box x5", "cost": 450, "plays": 5},
    {"key": "G12", "label": "Mystery Box x12", "cost": 1000, "plays": 12},
]

MYSTERY_BOX_PITY_RULES = {
    "standard": {
        "field": "standard_voucher_pity",
        "threshold": 6,
        "boost_multiplier": 2.5,
        "label": "Standard Box",
    },
    "premium": {
        "field": "premium_voucher_pity",
        "threshold": 4,
        "boost_multiplier": 2.0,
        "label": "Premium Box",
    },
}

PASSWORD_RESET_OTP_SESSION_KEY = "password_reset_verified_otp_id"
PASSWORD_RESET_OTP_EXPIRY_MINUTES = 10
PASSWORD_RESET_OTP_MAX_ATTEMPTS = 5
PASSWORD_RESET_OTP_RESEND_SECONDS = 60


def _require_reward_admin(user):
    if not (user.is_staff or user.is_superuser):
        raise PermissionDenied


def _generate_email_otp():
    return f"{random.randint(0, 999999):06d}"


def _mask_email(email):
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "*" * max(0, len(local) - 1)
    else:
        masked_local = local[:2] + "*" * (len(local) - 2)
    return f"{masked_local}@{domain}"


def _clear_password_reset_session(request):
    request.session.pop(PASSWORD_RESET_OTP_SESSION_KEY, None)


def _get_latest_password_reset_otp(email):
    if not email:
        return None
    return (
        PasswordResetOTP.objects
        .filter(email__iexact=email)
        .select_related("user")
        .order_by("-created_at")
        .first()
    )


def _get_resend_wait_seconds(email):
    latest_otp = _get_latest_password_reset_otp(email)
    if not latest_otp:
        return 0
    return latest_otp.resend_available_in(PASSWORD_RESET_OTP_RESEND_SECONDS)


def _issue_password_reset_otp(user):
    latest_otp = _get_latest_password_reset_otp(user.email)
    resend_wait_seconds = latest_otp.resend_available_in(PASSWORD_RESET_OTP_RESEND_SECONDS) if latest_otp else 0
    if resend_wait_seconds > 0:
        return None, resend_wait_seconds

    raw_otp = _generate_email_otp()
    PasswordResetOTP.objects.filter(user=user, used=False).update(used=True)
    otp = PasswordResetOTP.objects.create(
        user=user,
        email=user.email,
        code=make_password(raw_otp),
        expires_at=PasswordResetOTP.build_expiry(PASSWORD_RESET_OTP_EXPIRY_MINUTES),
    )
    return (otp, raw_otp), 0


def _send_password_reset_otp_email(user, otp_code):
    send_mail(
        subject="Ma OTP dat lai mat khau QShop",
        message=(
            f"Xin chao {user.username},\n\n"
            f"Ma OTP dat lai mat khau cua ban la: {otp_code}\n"
            f"Ma co hieu luc trong {PASSWORD_RESET_OTP_EXPIRY_MINUTES} phut.\n"
            "Neu ban khong yeu cau, hay bo qua email nay."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )



# Create your views here.
def user_login(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            user = authenticate(request, username=data['username'], password=data['password'])
            if user is not None:
                login(request, user)
                return redirect('shops:index')
            else:
                messages.error(request, 'Invalid username or password.')
                return render(request, 'users/login.html', {'form': form})
    else:
        form = LoginForm()
    return render(request, 'users/login.html', {'form': form})

def index(request):
    return render(request, 'users/index.html')

def register(request):
    if request.method == 'POST':
        user_form = UserRegistrationForm(request.POST)
        if user_form.is_valid():
            new_user = user_form.save(commit=False)
            new_user.set_password(user_form.cleaned_data['password'])

            new_user.is_staff = False
            new_user.is_superuser = False

            new_user.save()

            Profile.objects.create(user=new_user)

            try:
                customer_group = Group.objects.get(name='Customer')
                new_user.groups.add(customer_group)
            except Group.DoesNotExist:
                pass

            return render(request, 'users/register_done.html', {'new_user': new_user})
    else:
        user_form = UserRegistrationForm()

    return render(request, 'users/register.html', {'user_form': user_form})


def password_reset_request(request):
    if request.user.is_authenticated:
        return redirect("shops:index")

    if request.method == "POST":
        form = PasswordResetOTPRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            user = (
                User.objects
                .filter(email__iexact=email, is_active=True)
                .order_by("id")
                .first()
            )
            _clear_password_reset_session(request)

            if user:
                issued_payload, resend_wait_seconds = _issue_password_reset_otp(user)
                if resend_wait_seconds > 0:
                    messages.error(request, f"Vui lòng chờ {resend_wait_seconds} giây trước khi yêu cầu OTP mới.")
                    return redirect(f"{reverse('users:password_reset_verify')}?email={email}")
                try:
                    otp, raw_otp = issued_payload
                    _send_password_reset_otp_email(user, raw_otp)
                except Exception:
                    otp.delete()
                    messages.error(request, "Không thể gửi OTP qua email lúc này. Vui lòng thử lại sau.")
                    return render(request, "users/password_reset_form.html", {"form": form})

            return redirect(f"{reverse('users:password_reset_verify')}?email={email}")
    else:
        form = PasswordResetOTPRequestForm()

    return render(request, "users/password_reset_form.html", {"form": form})


def password_reset_verify(request):
    if request.user.is_authenticated:
        return redirect("shops:index")

    initial_email = request.GET.get("email", "").strip().lower()
    if request.method == "POST":
        form = PasswordResetOTPVerifyForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            otp_code = form.cleaned_data["otp"]
            otp = (
                PasswordResetOTP.objects
                .filter(email__iexact=email, used=False)
                .select_related("user")
                .order_by("-created_at")
                .first()
            )

            if not otp or not check_password(otp_code, otp.code):
                if otp:
                    otp.attempts += 1
                    if otp.attempts >= PASSWORD_RESET_OTP_MAX_ATTEMPTS:
                        otp.used = True
                    otp.save(update_fields=["attempts", "used"])
                messages.error(request, "OTP không hợp lệ.")
            elif otp.is_expired():
                otp.used = True
                otp.save(update_fields=["used"])
                messages.error(request, "OTP đã hết hạn. Vui lòng yêu cầu mã mới.")
            elif otp.attempts >= PASSWORD_RESET_OTP_MAX_ATTEMPTS:
                otp.used = True
                otp.save(update_fields=["used"])
                messages.error(request, "OTP đã bị khóa sau quá nhiều lần nhập sai.")
            else:
                request.session[PASSWORD_RESET_OTP_SESSION_KEY] = otp.id
                return redirect("users:password_reset_confirm")
    else:
        form = PasswordResetOTPVerifyForm(initial={"email": initial_email})

    return render(
        request,
        "users/password_reset_done.html",
        {
            "form": form,
            "masked_email": _mask_email(initial_email) if initial_email else "",
            "verify_email": initial_email,
            "otp_expiry_minutes": PASSWORD_RESET_OTP_EXPIRY_MINUTES,
            "resend_wait_seconds": _get_resend_wait_seconds(initial_email),
            "resend_cooldown_seconds": PASSWORD_RESET_OTP_RESEND_SECONDS,
        },
    )


@require_POST
def password_reset_resend(request):
    if request.user.is_authenticated:
        return redirect("shops:index")

    email = request.POST.get("email", "").strip().lower()
    if not email:
        messages.error(request, "Thiếu email để gửi lại OTP.")
        return redirect("users:password_reset")

    user = (
        User.objects
        .filter(email__iexact=email, is_active=True)
        .order_by("id")
        .first()
    )
    if not user:
        return redirect(f"{reverse('users:password_reset_verify')}?email={email}")

    issued_payload, resend_wait_seconds = _issue_password_reset_otp(user)
    if resend_wait_seconds > 0:
        messages.error(request, f"Vui lòng chờ {resend_wait_seconds} giây trước khi gửi lại OTP.")
        return redirect(f"{reverse('users:password_reset_verify')}?email={email}")

    otp, raw_otp = issued_payload
    try:
        _send_password_reset_otp_email(user, raw_otp)
        messages.success(request, "OTP mới đã được gửi tới email của bạn.")
    except Exception:
        otp.delete()
        messages.error(request, "Không thể gửi lại OTP lúc này. Vui lòng thử lại sau.")

    return redirect(f"{reverse('users:password_reset_verify')}?email={email}")


def password_reset_confirm(request):
    if request.user.is_authenticated:
        return redirect("shops:index")

    otp_id = request.session.get(PASSWORD_RESET_OTP_SESSION_KEY)
    if not otp_id:
        messages.error(request, "Phiên xác minh không hợp lệ. Vui lòng yêu cầu OTP mới.")
        return redirect("users:password_reset")

    otp = (
        PasswordResetOTP.objects
        .filter(id=otp_id, used=False)
        .select_related("user")
        .first()
    )
    if not otp or otp.is_expired():
        if otp:
            otp.used = True
            otp.save(update_fields=["used"])
        _clear_password_reset_session(request)
        messages.error(request, "OTP đã hết hạn hoặc không còn hợp lệ. Vui lòng yêu cầu lại.")
        return redirect("users:password_reset")

    if request.method == "POST":
        form = PasswordResetOTPSetPasswordForm(request.POST, user=otp.user)
        if form.is_valid():
            otp.user.set_password(form.cleaned_data["new_password1"])
            otp.user.save(update_fields=["password"])
            otp.used = True
            otp.save(update_fields=["used"])
            _clear_password_reset_session(request)
            return redirect("users:password_reset_complete")
    else:
        form = PasswordResetOTPSetPasswordForm(user=otp.user)

    return render(
        request,
        "users/password_reset_confirm.html",
        {
            "form": form,
            "masked_email": _mask_email(otp.email),
        },
    )


def password_reset_complete(request):
    return render(request, "users/password_reset_complete.html")


@login_required
def edit(request):
    try:
        profile = request.user.profile
    except Profile.DoesNotExist:
        profile = Profile.objects.create(user=request.user)
    if request.method == 'POST':
        user_form = UserEditForm(instance=request.user, data=request.POST)
        profile_form = ProfileEditForm(instance=profile, data=request.POST, files=request.FILES)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Profile updated successfully')
            return redirect('shops:index')
        else:
            messages.error(request, 'Error updating your profile')
    else:
        user_form = UserEditForm(instance=request.user)
        profile_form = ProfileEditForm(instance=profile)
    return render(request, 'users/edit.html', {'user_form': user_form, 'profile_form': profile_form})

@login_required
def profile(request):
    user = request.user
    profile_obj = update_user_rank_realtime(user)
    total_orders = user.orders.count()
    shipping_orders = user.orders.filter(
        status="Shipped"
    ).count()
    total_spent = (
        user.orders
        .filter(paid=True)
        .aggregate(total=Sum("total_price"))["total"] or 0
    )
    rank_info = get_next_rank_info(profile_obj.lifetime_points)
    recent_exchanges = user.point_exchanges.all()[:8]

    context = {
        "total_orders": total_orders,
        "shipping_orders": shipping_orders,
        "total_spent": total_spent,
        "points": profile_obj.points,
        "lifetime_points": profile_obj.lifetime_points,
        "rank": profile_obj.rank,
        "minigame_plays": profile_obj.minigame_plays,
        "rank_info": rank_info,
        "recent_exchanges": recent_exchanges
    }
    
    return render(request, "users/profile.html", context)


@login_required
def rewards(request):
    profile_obj = update_user_rank_realtime(request.user)
    now = timezone.now()

    expiring_24h = Coupon.objects.filter(
        owner=request.user,
        active=True,
        valid_to__gt=now,
        valid_to__lte=now + timedelta(hours=24)
    )

    expiring_72h = Coupon.objects.filter(
        owner=request.user,
        active=True,
        valid_to__gt=now + timedelta(hours=24),
        valid_to__lte=now + timedelta(hours=72)
    )
    owned_vouchers = (
        Coupon.objects
        .filter(
            owner=request.user,
            active=True,
            valid_from__lte=now,
            valid_to__gte=now
        )
        .exclude(couponusage__user=request.user)
        .order_by("valid_to")
    )

    context = {
        "points": profile_obj.points,
        "minigame_plays": profile_obj.minigame_plays,
        "voucher_options": RewardVoucherOption.objects.filter(active=True).order_by("sort_order", "id"),
        "minigame_options": MINIGAME_OPTIONS,
        "owned_vouchers": owned_vouchers,
        "expiring_24h" : expiring_24h,
        "expiring_72h" : expiring_72h,
        "recent_exchanges": request.user.point_exchanges.all()[:10],
    }
    return render(request, "users/rewards.html", context)


@login_required
def reward_admin_console(request):
    _require_reward_admin(request.user)

    selected_box = request.GET.get("box", "standard").strip().lower()
    if selected_box not in {"standard", "premium"}:
        selected_box = "standard"

    context = {
        "selected_box_type": selected_box,
        "voucher_options": RewardVoucherOption.objects.all().order_by("sort_order", "id"),
        "mystery_rewards": MysteryBoxRewardOption.objects.all().order_by("box_tier", "sort_order", "id"),
    }
    return render(request, "users/reward_admin_console.html", context)


@login_required
@require_POST
def manage_voucher_options(request):
    _require_reward_admin(request.user)

    action = request.POST.get("action", "").strip()

    def parse_int(name, default=0):
        raw = request.POST.get(name, "").strip()
        if raw == "":
            return default
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"Giá trị {name} không hợp lệ.")

    try:
        if action == "create":
            row = RewardVoucherOption(
                name=request.POST.get("name", "").strip() or "Voucher mới",
                cost_points=max(1, parse_int("cost_points", 1)),
                discount=max(1, min(100, parse_int("discount", 1))),
                max_discount=max(0, parse_int("max_discount", 0)),
                valid_days=max(1, parse_int("valid_days", 1)),
                sort_order=max(0, parse_int("sort_order", 0)),
                active=bool(request.POST.get("active")),
            )
            row.save()
            messages.success(request, "Đã thêm gói voucher.")

        elif action == "update":
            option_id = parse_int("option_id")
            row = RewardVoucherOption.objects.get(id=option_id)
            row.name = request.POST.get("name", row.name).strip() or row.name
            row.cost_points = max(1, parse_int("cost_points", row.cost_points))
            row.discount = max(1, min(100, parse_int("discount", row.discount)))
            row.max_discount = max(0, parse_int("max_discount", row.max_discount))
            row.valid_days = max(1, parse_int("valid_days", row.valid_days))
            row.sort_order = max(0, parse_int("sort_order", row.sort_order))
            row.active = bool(request.POST.get("active"))
            row.save()
            messages.success(request, "Đã cập nhật gói voucher.")

        elif action == "toggle":
            option_id = parse_int("option_id")
            row = RewardVoucherOption.objects.get(id=option_id)
            row.active = not row.active
            row.save(update_fields=["active"])
            messages.success(request, "Đã đổi trạng thái gói voucher.")
        else:
            messages.error(request, "Action không hợp lệ.")

    except RewardVoucherOption.DoesNotExist:
        messages.error(request, "Không tìm thấy gói voucher.")
    except ValueError as ex:
        messages.error(request, str(ex))
    except Exception:
        messages.error(request, "Không thể lưu gói voucher. Vui lòng kiểm tra dữ liệu.")

    return redirect("users:reward_admin_console")


def _get_active_mystery_reward_pool(box_tier="STANDARD"):
    rewards = []
    for row in MysteryBoxRewardOption.objects.filter(
        active=True,
        weight__gt=0,
        box_tier=box_tier
    ).order_by("sort_order", "id"):
        rewards.append({
            "type": row.reward_type,
            "label": row.name,
            "weight": row.weight,
            "points_value": row.points_value,
            "plays_value": row.plays_value,
            "voucher_discount": row.voucher_discount,
            "voucher_max_discount": row.voucher_max_discount,
            "voucher_valid_days": row.voucher_valid_days,
        })
    return rewards


def _get_box_reward_odds(box_tier):
    pool = _get_active_mystery_reward_pool(box_tier)
    total_weight = sum(item["weight"] for item in pool)
    grouped_weights = {}
    for item in pool:
        grouped_weights[item["type"]] = grouped_weights.get(item["type"], 0) + item["weight"]

    odds = []
    for reward_type in ["POINTS", "PLAYS", "VOUCHER", "EMPTY"]:
        weight = grouped_weights.get(reward_type, 0)
        odds.append({
            "type": reward_type,
            "weight": weight,
            "percent": (weight * 100 / total_weight) if total_weight else 0,
        })
    return odds


def _get_box_pity_status(profile_obj, box_type):
    config = MYSTERY_BOX_PITY_RULES[box_type]
    misses = getattr(profile_obj, config["field"], 0)
    threshold = config["threshold"]
    guaranteed_in = max(0, threshold - misses)
    return {
        "misses": misses,
        "threshold": threshold,
        "guaranteed_in": guaranteed_in,
        "progress_percent": min(100, int(misses * 100 / threshold)) if threshold else 0,
        "box_label": config["label"],
    }


def _build_weighted_reward_pool(base_pool, pity_misses, threshold, boost_multiplier):
    if not base_pool or pity_misses <= 0 or threshold <= 1:
        return [dict(item) for item in base_pool]

    weighted_pool = []
    progress = min(pity_misses, threshold - 1) / (threshold - 1)
    voucher_multiplier = 1 + (boost_multiplier - 1) * progress

    for item in base_pool:
        cloned = dict(item)
        if cloned["type"] == "VOUCHER":
            cloned["weight"] = max(1, int(round(cloned["weight"] * voucher_multiplier)))
        weighted_pool.append(cloned)
    return weighted_pool


def _generate_mystery_board():
    pool = _get_active_mystery_reward_pool("STANDARD")
    if not pool:
        return []
    weights = [item["weight"] for item in pool]
    board = []
    for _ in range(9):
        picked = random.choices(pool, weights=weights, k=1)[0]
        board.append({
            "type": picked["type"],
            "label": picked["label"],
            "points_value": picked["points_value"],
            "plays_value": picked["plays_value"],
            "voucher_discount": picked["voucher_discount"],
            "voucher_max_discount": picked["voucher_max_discount"],
            "voucher_valid_days": picked["voucher_valid_days"],
        })
    return board


@login_required
def minigame(request):
    profile_obj = update_user_rank_realtime(request.user)
    can_use_premium_box = profile_obj.rank in PREMIUM_BOX_ALLOWED_RANKS
    selected_box_type = request.GET.get("box", "standard").strip().lower()
    if selected_box_type not in {"standard", "premium"}:
        selected_box_type = "standard"
    if selected_box_type == "premium" and not can_use_premium_box:
        selected_box_type = "standard"

    context = {
        "minigame_plays": profile_obj.minigame_plays,
        "open_options": [1, 3, 5],
        "recent_box_histories": request.user.mystery_box_histories.all()[:12],
        "can_use_premium_box": can_use_premium_box,
        "selected_box_type": selected_box_type,
        "current_rank": profile_obj.rank,
        "reward_odds": _get_box_reward_odds("PREMIUM" if selected_box_type == "premium" else "STANDARD"),
        "pity_status": _get_box_pity_status(profile_obj, selected_box_type),
    }
    return render(request, "users/minigame.html", context)


def _apply_mystery_reward(profile_obj, user, reward):
    extra = ""

    if reward["type"] == "POINTS":
        profile_obj.points += reward.get("points_value", 0)

    elif reward["type"] == "PLAYS":
        profile_obj.minigame_plays += reward.get("plays_value", 0)

    elif reward["type"] == "VOUCHER":
        discount = reward.get("voucher_discount", 0)
        if discount <= 0:
            return extra
        now = timezone.now()
        coupon = Coupon.objects.create(
            owner=user,
            code=_generate_coupon_code(),
            valid_from=now,
            valid_to=now + timedelta(days=max(1, reward.get("voucher_valid_days", 1))),
            discount=discount,
            max_discount=reward.get("voucher_max_discount", 0),
            usage_limit=1,
            active=True
        )
        extra = coupon.code

    return extra


@login_required
@require_POST
def open_mystery_box(request):
    try:
        open_count = int(request.POST.get("open_count", "1"))
    except ValueError:
        return JsonResponse({"ok": False, "error": "So hop mo khong hop le."}, status=400)

    try:
        clicked_index = int(request.POST.get("clicked_index", "-1"))
    except ValueError:
        return JsonResponse({"ok": False, "error": "Vi tri hop khong hop le."}, status=400)

    if open_count not in {1, 3, 5}:
        return JsonResponse({"ok": False, "error": "Chi duoc mo 1, 3 hoac 5 hop."}, status=400)
    if clicked_index < 0 or clicked_index > 8:
        return JsonResponse({"ok": False, "error": "Vi tri hop khong hop le."}, status=400)

    box_type = request.POST.get("box_type", "standard").strip().lower()
    if box_type not in {"standard", "premium"}:
        return JsonResponse({"ok": False, "error": "Loai box khong hop le."}, status=400)

    with transaction.atomic():
        profile_obj = Profile.objects.select_for_update().get(user=request.user)

        if box_type == "premium" and profile_obj.rank not in PREMIUM_BOX_ALLOWED_RANKS:
            return JsonResponse({"ok": False, "error": "Premium Box chi mo cho rank Gold Buyer tro len."}, status=403)

        if profile_obj.minigame_plays < open_count:
            return JsonResponse({"ok": False, "error": f"Ban can it nhat {open_count} luot choi."}, status=400)

        profile_obj.minigame_plays -= open_count
        pity_config = MYSTERY_BOX_PITY_RULES[box_type]
        pity_field = pity_config["field"]
        pity_misses = getattr(profile_obj, pity_field, 0)

        # New board is generated per turn, then discarded after opening.
        box_tier = "PREMIUM" if box_type == "premium" else "STANDARD"
        board = _get_active_mystery_reward_pool(box_tier)
        weighted_board = _build_weighted_reward_pool(
            board,
            pity_misses=pity_misses,
            threshold=pity_config["threshold"],
            boost_multiplier=pity_config["boost_multiplier"],
        )
        if board:
            weights = [item["weight"] for item in weighted_board]
            generated_board = []
            for _ in range(9):
                generated_board.append(random.choices(weighted_board, weights=weights, k=1)[0])
            board = generated_board
        if not board:
            box_label = "Premium Box" if box_type == "premium" else "Standard Box"
            return JsonResponse({"ok": False, "error": f"Admin chua cau hinh phan qua cho {box_label}."}, status=400)
        remaining_indexes = [i for i in range(9) if i != clicked_index]
        chosen_indexes = [clicked_index]
        if open_count > 1:
            chosen_indexes.extend(random.sample(remaining_indexes, k=open_count - 1))
        pity_triggered = False
        voucher_pool = [item for item in weighted_board if item["type"] == "VOUCHER"]
        chosen_rewards = [board[idx] for idx in chosen_indexes]
        guarantee_voucher = (
            bool(voucher_pool)
            and pity_misses + 1 >= pity_config["threshold"]
            and not any(item["type"] == "VOUCHER" for item in chosen_rewards)
        )
        if guarantee_voucher:
            voucher_weights = [item["weight"] for item in voucher_pool]
            board[chosen_indexes[-1]] = random.choices(voucher_pool, weights=voucher_weights, k=1)[0]
            chosen_rewards[-1] = board[chosen_indexes[-1]]
            pity_triggered = True
        rewards = []

        for idx, reward in zip(chosen_indexes, chosen_rewards):
            extra = _apply_mystery_reward(profile_obj, request.user, reward)

            label = reward["label"]
            if reward["type"] == "VOUCHER" and extra:
                label = f"{reward['label']} - ma {extra}"

            rewards.append({
                "index": idx,
                "label": label,
                "type": reward["type"],
            })

        if any(item["type"] == "VOUCHER" for item in chosen_rewards):
            setattr(profile_obj, pity_field, 0)
        else:
            setattr(profile_obj, pity_field, pity_misses + 1)

        profile_obj.save(update_fields=["points", "minigame_plays", pity_field])
        MysteryBoxHistory.objects.create(
            user=request.user,
            open_count=open_count,
            rewards=[r["label"] for r in rewards]
        )

    return JsonResponse({
        "ok": True,
        "rewards": rewards,
        "remaining_plays": profile_obj.minigame_plays,
        "opened_count": open_count,
        "pity_triggered": pity_triggered,
        "pity_status": _get_box_pity_status(profile_obj, box_type),
    })


@login_required
@require_POST
def manage_mystery_rewards(request):
    _require_reward_admin(request.user)

    action = request.POST.get("action", "").strip()
    selected_box = request.POST.get("selected_box_type", "standard").strip().lower()
    if selected_box not in {"standard", "premium"}:
        selected_box = "standard"

    def parse_int(name, default=0):
        raw = request.POST.get(name, "").strip()
        if raw == "":
            return default
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"Giá trị {name} không hợp lệ.")

    try:
        if action == "create":
            row = MysteryBoxRewardOption(
                name=request.POST.get("name", "").strip() or "Phần quà mới",
                box_tier=request.POST.get("box_tier", "STANDARD"),
                reward_type=request.POST.get("reward_type", "EMPTY"),
                points_value=max(0, parse_int("points_value")),
                plays_value=max(0, parse_int("plays_value")),
                voucher_discount=max(0, parse_int("voucher_discount")),
                voucher_max_discount=max(0, parse_int("voucher_max_discount")),
                voucher_valid_days=max(0, parse_int("voucher_valid_days")),
                weight=max(1, parse_int("weight", 1)),
                sort_order=max(0, parse_int("sort_order", 0)),
                active=bool(request.POST.get("active")),
            )
            if row.box_tier not in {"STANDARD", "PREMIUM"}:
                raise ValueError("Box tier không hợp lệ.")
            if row.reward_type not in {"POINTS", "PLAYS", "VOUCHER", "EMPTY"}:
                raise ValueError("Reward type không hợp lệ.")
            row.save()
            messages.success(request, "Đã thêm phần quà mới.")

        elif action == "update":
            reward_id = parse_int("reward_id")
            row = MysteryBoxRewardOption.objects.get(id=reward_id)
            row.name = request.POST.get("name", row.name).strip() or row.name
            row.box_tier = request.POST.get("box_tier", row.box_tier)
            row.reward_type = request.POST.get("reward_type", row.reward_type)
            row.points_value = max(0, parse_int("points_value", row.points_value))
            row.plays_value = max(0, parse_int("plays_value", row.plays_value))
            row.voucher_discount = max(0, parse_int("voucher_discount", row.voucher_discount))
            row.voucher_max_discount = max(0, parse_int("voucher_max_discount", row.voucher_max_discount))
            row.voucher_valid_days = max(0, parse_int("voucher_valid_days", row.voucher_valid_days))
            row.weight = max(1, parse_int("weight", row.weight))
            row.sort_order = max(0, parse_int("sort_order", row.sort_order))
            row.active = bool(request.POST.get("active"))

            if row.box_tier not in {"STANDARD", "PREMIUM"}:
                raise ValueError("Box tier không hợp lệ.")
            if row.reward_type not in {"POINTS", "PLAYS", "VOUCHER", "EMPTY"}:
                raise ValueError("Reward type không hợp lệ.")
            row.save()
            messages.success(request, "Đã cập nhật phần quà.")

        elif action == "toggle":
            reward_id = parse_int("reward_id")
            row = MysteryBoxRewardOption.objects.get(id=reward_id)
            row.active = not row.active
            row.save(update_fields=["active"])
            messages.success(request, "Đã đổi trạng thái phần quà.")
        else:
            messages.error(request, "Action không hợp lệ.")

    except MysteryBoxRewardOption.DoesNotExist:
        messages.error(request, "Không tìm thấy phần quà cần sửa.")
    except ValueError as ex:
        messages.error(request, str(ex))
    except Exception:
        messages.error(request, "Không thể lưu phần quà. Vui lòng kiểm tra dữ liệu.")

    return redirect(f"{reverse('users:reward_admin_console')}?box={selected_box}")

def get_next_rank_info(points):

    ranks = [
        (0, "Newbie"),
        (100, "Explorer"),
        (300, "Shopper"),
        (700, "Regular"),
        (1500, "Premium"),
        (3000, "Gold Buyer"),
        (6000, "Platinum Buyer"),
        (12000, "Diamond Buyer"),
        (25000, "Elite Buyer"),
        (50000, "Legend Buyer"),
    ]

    next_rank = None
    next_points = None

    for p, name in ranks:
        if points < p:
            next_points = p
            next_rank = name
            break

    if next_points is None:
        return None

    needed = next_points - points

    progress = int(points / next_points * 100)

    return {
        "next_rank": next_rank,
        "needed_points": needed,
        "progress": progress,
    }


def _generate_coupon_code():
    return f"RWD{uuid.uuid4().hex[:8].upper()}"


@login_required
@require_POST
def redeem_points_voucher(request):
    option_id = request.POST.get("voucher_option")
    option = RewardVoucherOption.objects.filter(id=option_id, active=True).first()
    if not option:
        messages.error(request, "Gói voucher không hợp lệ.")
        return redirect("users:rewards")

    now = timezone.now()

    with transaction.atomic():
        profile_obj = Profile.objects.select_for_update().get(user=request.user)

        if profile_obj.points < option.cost_points:
            messages.error(request, "Bạn không đủ điểm để đổi voucher.")
            return redirect("users:rewards")

        profile_obj.points -= option.cost_points
        profile_obj.save(update_fields=["points"])

        coupon = Coupon.objects.create(
            owner=request.user,
            code=_generate_coupon_code(),
            valid_from=now,
            valid_to=now + timedelta(days=option.valid_days),
            discount=option.discount,
            max_discount=option.max_discount,
            usage_limit=1,
            active=True
        )

        PointExchange.objects.create(
            user=request.user,
            exchange_type=PointExchange.TYPE_VOUCHER,
            points_spent=option.cost_points,
            note=f"{coupon.code} - {option.discount}% (tối đa {option.max_discount:,}d)"
        )

    messages.success(
        request,
        f"Đổi voucher thành công: {coupon.code} ({option.discount}%), hiệu lực {option.valid_days} ngày."
    )
    return redirect("users:rewards")


@login_required
@require_POST
def redeem_points_minigame(request):
    game_options = {item["key"]: item for item in MINIGAME_OPTIONS}
    option_key = request.POST.get("minigame_option")
    option = game_options.get(option_key)
    if not option:
        messages.error(request, "Gói lượt chơi không hợp lệ.")
        return redirect("users:rewards")

    with transaction.atomic():
        profile_obj = Profile.objects.select_for_update().get(user=request.user)

        if profile_obj.points < option["cost"]:
            messages.error(request, "Bạn không đủ điểm để đổi lượt chơi minigame.")
            return redirect("users:rewards")

        profile_obj.points -= option["cost"]
        profile_obj.minigame_plays += option["plays"]
        profile_obj.save(update_fields=["points", "minigame_plays"])

        PointExchange.objects.create(
            user=request.user,
            exchange_type=PointExchange.TYPE_MINIGAME,
            points_spent=option["cost"],
            note=f"+{option['plays']} lượt chơi minigame"
        )

    messages.success(
        request,
        f"Đổi thành công {option['plays']} lượt chơi minigame."
    )
    return redirect("users:rewards")

def get_rank_benefits(self):

    benefits = {

        "Newbie": {
            "discount": 0,
            "max_discount": 0,
        },

        "Explorer": {
            "discount": 0.5,
            "max_discount": 200_000,
        },

        "Shopper": {
            "discount": 1,
            "max_discount": 500_000,
        },

        "Regular": {
            "discount": 1.5,
            "max_discount": 800_000,
        },

        "Premium": {
            "discount": 2,
            "max_discount": 1_500_000,
        },

        "Gold Buyer": {
            "discount": 3,
            "max_discount": 2_000_000,
        },

        "Platinum Buyer": {
            "discount": 4,
            "max_discount": 3_000_000,
        },

        "Diamond Buyer": {
            "discount": 5,
            "max_discount": 4_000_000,
        },

        "Elite Buyer": {
            "discount": 6,
            "max_discount": 5_000_000,
        },

        "Legend Buyer": {
            "discount": 7,
            "max_discount": 7_000_000,
        },

    }

    return benefits.get(self.rank)
