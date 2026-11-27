from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from monitor.models import phone_validator
from monitor.sms import send_sms, sms_config_problem


class Command(BaseCommand):
    help = "Send one test SMS and write it to the SMS log."

    def add_arguments(self, parser):
        parser.add_argument("phone", help="Number in international format, e.g. +639171234567")
        parser.add_argument(
            "--text",
            default="HydroHomie system check. Please ignore this message.",
            help="Message text.",
        )

    def handle(self, *args, **options):
        phone = options["phone"]
        try:
            phone_validator(phone)
        except ValidationError:
            raise CommandError("Use international format, for example +639171234567.")

        problem = sms_config_problem()
        if problem:
            self.stdout.write(self.style.WARNING(problem))

        log = send_sms(phone, options["text"])
        self.stdout.write(f"Status: {log.status}")
        if log.provider_sid:
            self.stdout.write(f"Twilio message ID: {log.provider_sid}")
        if log.error_message:
            self.stdout.write(self.style.ERROR(f"Error: {log.error_message}"))