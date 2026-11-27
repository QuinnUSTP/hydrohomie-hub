from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from .models import Alert, AlertThreshold, Resident, SensorNode, SMSLog
from .services import save_reading

SMS_ON = dict(
    SMS_ENABLED=True,
    SMS_ASYNC=False,
    TWILIO_ACCOUNT_SID="ACtest",
    TWILIO_AUTH_TOKEN="token",
    TWILIO_FROM="+15005550006",
    TWILIO_MESSAGING_SERVICE_SID="",
)


def fake_client(status="queued"):
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(sid="SM123", status=status)
    return client


@override_settings(**SMS_ON)
class AlertSmsTests(TestCase):
    def setUp(self):
        self.z1 = SensorNode.objects.create(node_id="Z1", name="Zone 1", location="Purok 1")
        self.z2 = SensorNode.objects.create(node_id="Z2", name="Zone 2")
        AlertThreshold.objects.create(node=self.z1, alert_distance_cm=30, cooldown_minutes=30)
        self.r1 = Resident.objects.create(
            full_name="A", phone_number="+639170000001", node=self.z1
        )
        self.r2 = Resident.objects.create(
            full_name="B", phone_number="+639170000002", node=self.z2
        )
        self.r3 = Resident.objects.create(
            full_name="C", phone_number="+639170000003", node=self.z1, receives_sms=False
        )
        self.r4 = Resident.objects.create(full_name="D", phone_number="+639170000004")

    def run_alert(self, client):
        with patch("monitor.sms._make_client", return_value=client):
            save_reading(self.z1, 20.0, True)

    def test_sends_to_right_residents_only(self):
        client = fake_client()
        self.run_alert(client)
        sent = sorted(c.kwargs["to"] for c in client.messages.create.call_args_list)
        self.assertEqual(sent, ["+639170000001", "+639170000004"])

    def test_every_message_is_logged(self):
        self.run_alert(fake_client())
        logs = SMSLog.objects.all()
        self.assertEqual(logs.count(), 2)
        for log in logs:
            self.assertEqual(log.status, "SENT")
            self.assertEqual(log.provider_sid, "SM123")
            self.assertEqual(log.direction, "OUT")
            self.assertIsNotNone(log.alert)

    def test_message_has_no_url_or_phone_number(self):
        client = fake_client()
        self.run_alert(client)
        body = client.messages.create.call_args.kwargs["body"]
        self.assertIn("Purok 1", body)
        self.assertNotIn("http", body)
        self.assertNotIn("+", body)

    def test_no_second_sms_while_alert_stays_active(self):
        client = fake_client()
        with patch("monitor.sms._make_client", return_value=client):
            save_reading(self.z1, 20.0, True)
            save_reading(self.z1, 18.0, True)
        self.assertEqual(client.messages.create.call_count, 2)

    def test_cooldown_blocks_repeat_blast(self):
        client = fake_client()
        with patch("monitor.sms._make_client", return_value=client):
            save_reading(self.z1, 20.0, True)
            save_reading(self.z1, 80.0, False)  # resolves
            save_reading(self.z1, 20.0, True)   # new alert inside cooldown
        self.assertEqual(Alert.objects.count(), 2)
        self.assertEqual(client.messages.create.call_count, 2)

    def test_zero_cooldown_allows_repeat_blast(self):
        AlertThreshold.objects.update(cooldown_minutes=0)
        client = fake_client()
        with patch("monitor.sms._make_client", return_value=client):
            save_reading(self.z1, 20.0, True)
            save_reading(self.z1, 80.0, False)
            save_reading(self.z1, 20.0, True)
        self.assertEqual(client.messages.create.call_count, 4)

    def test_twilio_error_is_logged_and_does_not_break_readings(self):
        client = MagicMock()
        client.messages.create.side_effect = Exception("Twilio down")
        self.run_alert(client)
        self.assertEqual(Alert.objects.filter(status="ACTIVE").count(), 1)
        self.assertEqual(SMSLog.objects.filter(status="FAILED").count(), 2)
        self.assertIn("Twilio down", SMSLog.objects.first().error_message)

    def test_failed_sms_does_not_start_cooldown(self):
        AlertThreshold.objects.update(cooldown_minutes=30)
        bad = MagicMock()
        bad.messages.create.side_effect = Exception("Twilio down")
        good = fake_client()
        with patch("monitor.sms._make_client", return_value=bad):
            save_reading(self.z1, 20.0, True)
            save_reading(self.z1, 80.0, False)
        with patch("monitor.sms._make_client", return_value=good):
            save_reading(self.z1, 20.0, True)
        self.assertEqual(good.messages.create.call_count, 2)

    def test_twilio_failed_status_is_marked_failed(self):
        self.run_alert(fake_client(status="failed"))
        self.assertEqual(SMSLog.objects.filter(status="FAILED").count(), 2)

    def test_messaging_service_is_used_when_set(self):
        client = fake_client()
        with override_settings(TWILIO_MESSAGING_SERVICE_SID="MG123"):
            self.run_alert(client)
        kwargs = client.messages.create.call_args.kwargs
        self.assertEqual(kwargs["messaging_service_sid"], "MG123")
        self.assertNotIn("from_", kwargs)

    def test_from_number_is_used_otherwise(self):
        client = fake_client()
        self.run_alert(client)
        self.assertEqual(client.messages.create.call_args.kwargs["from_"], "+15005550006")


class SmsOffTests(TestCase):
    @override_settings(**{**SMS_ON, "SMS_ENABLED": False})
    def test_disabled_logs_failure_and_never_calls_twilio(self):
        node = SensorNode.objects.create(node_id="Z1", name="Zone 1")
        AlertThreshold.objects.create(node=node, alert_distance_cm=30)
        Resident.objects.create(full_name="A", phone_number="+639170000001", node=node)
        with patch("monitor.sms._make_client") as make:
            save_reading(node, 20.0, True)
        make.assert_not_called()
        log = SMSLog.objects.get()
        self.assertEqual(log.status, "FAILED")
        self.assertIn("SMS_ENABLED", log.error_message)

    @override_settings(**{**SMS_ON, "TWILIO_AUTH_TOKEN": ""})
    def test_missing_key_logs_failure(self):
        from .sms import send_sms

        log = send_sms("+639170000001", "hello")
        self.assertEqual(log.status, "FAILED")
        self.assertIn("TWILIO_AUTH_TOKEN", log.error_message)