from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from .forms import LoginForm, UserRegistrationForm, UserEditForm, ProfileEditForm
from .models import (
    Profile,
    PointExchange,
    MysteryBoxHistory,
    RewardVoucherOption,
    MysteryBoxRewardOption,
)
from django.contrib import messages
from django.contrib.auth.models import Group
from shops.models import Order, Coupon
from django.db.models import Sum
from django.contrib.auth.decorators import login_required
from shops.rank_utils import update_user_rank_realtime
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction
from django.http import JsonResponse
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
        "manage_voucher_options": (
            RewardVoucherOption.objects.all().order_by("sort_order", "id")
            if request.user.is_staff or request.user.is_superuser
            else []
        ),
        
    }
    return render(request, "users/rewards.html", context)


@login_required
@require_POST
def manage_voucher_options(request):
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Bạn không có quyền chỉnh gói voucher.")
        return redirect("users:rewards")

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

    return redirect("users:rewards")


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
        "manage_rewards": (
            MysteryBoxRewardOption.objects.all().order_by("sort_order", "id")
            if request.user.is_staff or request.user.is_superuser
            else []
        ),
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

        # New board is generated per turn, then discarded after opening.
        board = _get_active_mystery_reward_pool("PREMIUM" if box_type == "premium" else "STANDARD")
        if board:
            weights = [item["weight"] for item in board]
            generated_board = []
            for _ in range(9):
                generated_board.append(random.choices(board, weights=weights, k=1)[0])
            board = generated_board
        if not board:
            box_label = "Premium Box" if box_type == "premium" else "Standard Box"
            return JsonResponse({"ok": False, "error": f"Admin chua cau hinh phan qua cho {box_label}."}, status=400)
        remaining_indexes = [i for i in range(9) if i != clicked_index]
        chosen_indexes = [clicked_index]
        if open_count > 1:
            chosen_indexes.extend(random.sample(remaining_indexes, k=open_count - 1))
        rewards = []

        for idx in chosen_indexes:
            reward = board[idx]
            extra = _apply_mystery_reward(profile_obj, request.user, reward)

            label = reward["label"]
            if reward["type"] == "VOUCHER" and extra:
                label = f"{reward['label']} - ma {extra}"

            rewards.append({
                "index": idx,
                "label": label,
                "type": reward["type"],
            })

        profile_obj.save(update_fields=["points", "minigame_plays"])
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
    })


@login_required
@require_POST
def manage_mystery_rewards(request):
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Bạn không có quyền chỉnh quà Mystery Box.")
        return redirect("users:minigame")

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

    return redirect(f"{reverse('users:minigame')}?box={selected_box}")

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


