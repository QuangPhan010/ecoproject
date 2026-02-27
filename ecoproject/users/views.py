from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from .forms import LoginForm, UserRegistrationForm, UserEditForm, ProfileEditForm
from .models import Profile
from django.contrib import messages
from django.contrib.auth.models import Group
from shops.models import Order
from django.db.models import Sum
from django.contrib.auth.decorators import login_required
from shops.rank_utils import update_user_rank_realtime




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
    update_user_rank_realtime(user)
    total_orders = user.orders.count()
    shipping_orders = user.orders.filter(
        status="Shipped"
    ).count()
    total_spent = (
        user.orders
        .filter(paid=True)
        .aggregate(total=Sum("total_price"))["total"] or 0
    )
    rank_info = get_next_rank_info(user.profile.points)

    context = {
        "total_orders": total_orders,
        "shipping_orders": shipping_orders,
        "total_spent": total_spent,
        "points": user.profile.points,
        "rank": user.profile.rank,
        "rank_info": rank_info,
    }
    
    return render(request, "users/profile.html", context)

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


