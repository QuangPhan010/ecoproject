from django.contrib.auth import get_user_model

from .models import UserNotification


def create_notification(*, user, notification_type, title, message="", target_url=""):
    if not user:
        return None

    return UserNotification.objects.create(
        user=user,
        notification_type=notification_type,
        title=title[:160],
        message=message,
        target_url=target_url,
    )


def notify_staff(*, notification_type, title, message="", target_url=""):
    user_model = get_user_model()
    staff_users = user_model.objects.filter(is_active=True).filter(is_staff=True) | user_model.objects.filter(
        is_active=True,
        is_superuser=True,
    )
    staff_users = staff_users.distinct()
    notifications = [
        UserNotification(
            user=user,
            notification_type=notification_type,
            title=title[:160],
            message=message,
            target_url=target_url,
        )
        for user in staff_users
    ]
    if notifications:
        UserNotification.objects.bulk_create(notifications)
