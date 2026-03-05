from django.core.management.base import BaseCommand

from shops.utils.order_expiry import expire_stale_pending_orders


class Command(BaseCommand):
    help = "Auto-cancel stale pending orders and release reserved stock."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=3,
            help="Expire pending orders older than this many hours (default: 3).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=200,
            help="Max number of stale orders processed per run (default: 200).",
        )

    def handle(self, *args, **options):
        hours = options["hours"]
        batch_size = options["batch_size"]
        expired = expire_stale_pending_orders(
            expire_hours=hours,
            batch_size=batch_size,
            logger=self,
        )
        self.stdout.write(self.style.SUCCESS(f"Expired {expired} stale pending order(s)."))

    # Logger-like adapter for service function
    def info(self, message, *args, **kwargs):
        if args:
            message = message % args
        self.stdout.write(message)

#python manage.py expire_stale_orders --hours 3 --batch-size 200

