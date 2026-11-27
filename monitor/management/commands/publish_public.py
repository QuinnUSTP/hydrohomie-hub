import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone

from monitor.models import PublishStatus
from monitor.publisher import config_problem, publish_once


class Command(BaseCommand):
    help = "Send the public snapshot to the public website every few seconds. Use --once for a single send."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Send one snapshot and exit.")

    def handle(self, *args, **options):
        problem = config_problem()
        if problem:
            raise CommandError(problem)
        interval = max(10, int(getattr(settings, "PUBLIC_PUBLISH_INTERVAL", 30)))
        failures = 0
        self.stdout.write(f"Publishing to {settings.PUBLIC_SITE_URL} every {interval} s. Press Ctrl+C to stop.")
        try:
            while True:
                close_old_connections()
                ok = publish_once()
                stamp = timezone.localtime().strftime("%H:%M:%S")
                if ok:
                    failures = 0
                    self.stdout.write(f"{stamp} sent")
                else:
                    failures += 1
                    error = PublishStatus.load().last_error
                    self.stdout.write(self.style.ERROR(f"{stamp} FAILED: {error}"))
                    if options["once"]:
                        raise CommandError(error)
                if options["once"]:
                    return
                time.sleep(interval if ok else min(60, interval * 2))
        except KeyboardInterrupt:
            self.stdout.write("Stopped.")