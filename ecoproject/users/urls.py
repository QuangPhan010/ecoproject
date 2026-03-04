"""
URL configuration for socialproject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path, reverse_lazy
from users import views
from django.contrib.auth import views as auth_view

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.user_login, name ='login'),
    path('logout/', auth_view.LogoutView.as_view(template_name='users/logout.html'), name='logout'),
    path('password_change/', auth_view.PasswordChangeView.as_view(template_name='users/password_change_form.html', success_url=reverse_lazy('password_change_done')), name='password_change'),
    path('password_change/done/', auth_view.PasswordChangeDoneView.as_view(template_name='users/password_change_done.html'), name='password_change_done'),

    # Password reset links
    path('password_reset/', auth_view.PasswordResetView.as_view(template_name='users/password_reset_form.html'), name='password_reset'),
    path('password_reset/done/', auth_view.PasswordResetDoneView.as_view(template_name='users/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_view.PasswordResetConfirmView.as_view(template_name='users/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_view.PasswordResetCompleteView.as_view(template_name='users/password_reset_complete.html'), name='password_reset_complete'),
    path('register/', views.register, name='register'),

    path('profile/', views.profile, name='profile'),
    path('rewards/', views.rewards, name='rewards'),
    path('rewards/voucher-options/manage/', views.manage_voucher_options, name='manage_voucher_options'),
    path('minigame/', views.minigame, name='minigame'),
    path('minigame/open-box/', views.open_mystery_box, name='open_mystery_box'),
    path('minigame/rewards/manage/', views.manage_mystery_rewards, name='manage_mystery_rewards'),
    path('edit/', views.edit, name='edit'),
    path('redeem/voucher/', views.redeem_points_voucher, name='redeem_points_voucher'),
    path('redeem/minigame/', views.redeem_points_minigame, name='redeem_points_minigame'),

]
