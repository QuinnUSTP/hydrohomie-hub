import logging
import threading
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.utils import timezone

from .models import Alert, AlertThreshold, Resident, SMSLog

logger = logging.getLogger(__name__)

# Seconds to wait for Twilio before giving up on one message.
SMS_TIMEOUT_SECONDS = 15


def sms_config_problem():
    """Return a short text describing what is missing, or None if all is set."""
    if not settings.SMS_ENABLED:
        return "SMS is turned off (SMS_ENABLED is not True in .env)."
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        return "TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN is missing in .env."
    if not settings.TWILIO_MESSAGING_SERVICE_SID and not settings.TWILIO_FROM:
        return "Set TWILIO_FROM or TWILIO_MESSAGING_SERVICE_SID in .env."
    return None


def _make_client():
    # Imported here so the project still starts if twilio is not installed.
    from twilio.http.http_client import TwilioHttpClient
    from twilio.rest import Client

    return Client(
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_AUTH_TOKEN,
        http_client=TwilioHttpClient(timeout=SMS_TIMEOUT_SECONDS),
    )


def send_sms(phone_number, body, resident=None, alert=None):
    """Send one SMS and ALWAYS write one SMSLog row. Never raises.

    The log row is saved first as QUEUED, then updated to SENT or FAILED.
    SENT means Twilio accepted the message. It does not prove the phone got it,
    because delivery reports need a public webhook URL (see the A8 notes).
    """
    log = SMSLog.objects.create(
        direction=SMSLog.Direction.OUTBOUND,
        phone_number=phone_number,
        body=body,
        status=SMSLog.Status.QUEUED,
        resident=resident,
        alert=alert,
    )

    problem = sms_config_problem()
    if problem:
        log.status = SMSLog.Status.FAILED
        log.error_message = problem
        log.save(update_fields=["status", "error_message"])
        return log

    try:
        client = _make_client()
        options = {"to": phone_number, "body": body}
        if settings.TWILIO_MESSAGING_SERVICE_SID:
            options["messaging_service_sid"] = settings.TWILIO_MESSAGING_SERVICE_SID
        else:
            options["from_"] = settings.TWILIO_FROM
        message = client.messages.create(**options)
    except Exception as exc:  # Twilio errors, network errors, bad settings
        logger.exception("SMS to %s failed", phone_number)
        log.status = SMSLog.Status.FAILED
        log.error_message = str(exc)[:500]
        log.save(update_fields=["status", "error_message"])
        return log

    log.provider_sid = message.sid or ""
    if message.status in ("failed", "undelivered"):
        log.status = SMSLog.Status.FAILED
        log.error_message = f"Twilio status: {message.status}"
    else:
        log.status = SMSLog.Status.SENT
    log.save(update_fields=["provider_sid", "status", "error_message"])
    return log


def build_alert_message(alert):
    """Plain fixed text. No URLs and no phone numbers (Philippine SMS rules)."""
    place = alert.node.location or alert.node.name or alert.node.node_id
    return (
        f"HydroHomie flood alert: water level is high near {place}. "
        "Move to higher ground and follow barangay instructions."
    )


def alert_recipients(alert):
    """Residents who opted in. A resident with no zone gets alerts from all zones."""
    return Resident.objects.filter(receives_sms=True).filter(
        Q(node=alert.node) | Q(node__isnull=True)
    )


def in_cooldown(alert):
    """True if an alert SMS for this node was already sent within the cooldown."""
    threshold = AlertThreshold.objects.filter(node=alert.node, is_active=True).first()
    minutes = threshold.cooldown_minutes if threshold else 0
    if minutes <= 0:
        return False
    since = timezone.now() - timedelta(minutes=minutes)
    return (
        SMSLog.objects.filter(alert__node=alert.node, created_at__gte=since)
        .exclude(alert=alert)
        .exclude(status=SMSLog.Status.FAILED)
        .exists()
    )


def notify_alert(alert):
    """Text every opted-in resident of the alert's zone. Returns the log rows."""
    if in_cooldown(alert):
        logger.info("Alert SMS for %s skipped: cooldown is active.", alert.node.node_id)
        return []
    body = build_alert_message(alert)
    return [
        send_sms(resident.phone_number, body, resident=resident, alert=alert)
        for resident in alert_recipients(alert)
    ]


def dispatch_alert_sms(alert):
    """Start sending without blocking the caller."""
    if not alert_recipients(alert).exists():
        return
    if not settings.SMS_ASYNC:
        notify_alert(alert)
        return

    alert_id = alert.pk

    def run():
        try:
            fresh = Alert.objects.select_related("node").get(pk=alert_id)
            notify_alert(fresh)
        except Exception:
            logger.exception("Alert SMS job failed for alert %s", alert_id)
        finally:
            connection.close()

    threading.Thread(target=run, name="alert-sms", daemon=True).start()