import io
import json
import urllib.error
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import Alert, AlertThreshold, Announcement, PublishStatus, Resident, SensorNode, SMSLog
from .publisher import PublishError, build_snapshot, config_problem, publish_once, send
from .services import save_reading

PUBLISH_ON = dict(PUBLIC_PUBLISH_ENABLED=True, PUBLIC_SITE_URL="https://example.org",
                  PUBLIC_SITE_TOKEN="secret-token-value")


@override_settings(SMS_ASYNC=False)
class SnapshotTests(TestCase):
    def setUp(self):
        self.z1 = SensorNode.objects.create(node_id="Z1", name="Zone 1", location="Purok 7 behind the secret mill",
                                            is_public=True, last_seen=timezone.now())
        AlertThreshold.objects.create(node=self.z1, alert_distance_cm=30)
        self.z2 = SensorNode.objects.create(node_id="Z2", name="Zone 2", is_public=False,
                                            last_seen=timezone.now())

    def zones(self):
        return {z["key"]: z for z in build_snapshot()["zones"]}

    def test_only_public_active_nodes_are_listed(self):
        self.assertEqual(list(self.zones()), ["z1"])
        SensorNode.objects.filter(pk=self.z1.pk).update(is_active=False)
        self.assertEqual(self.zones(), {})

    def test_node_without_readings_is_unknown(self):
        self.assertEqual(self.zones()["z1"]["state"], "unknown")

    def test_states_follow_the_sensor_rules(self):
        save_reading(self.z1, 80.0, False)
        self.assertEqual(self.zones()["z1"]["state"], "normal")
        save_reading(self.z1, 20.0, False)
        self.assertEqual(self.zones()["z1"]["state"], "watch")
        save_reading(self.z1, 20.0, True)
        self.assertEqual(self.zones()["z1"]["state"], "alert")
        save_reading(self.z1, 80.0, False)
        SensorNode.objects.filter(pk=self.z1.pk).update(last_seen=timezone.now() - timedelta(minutes=10))
        self.assertEqual(self.zones()["z1"]["state"], "offline")

    def test_water_level_needs_a_calibrated_sensor_height(self):
        save_reading(self.z1, 150.0, False)
        self.assertIsNone(self.zones()["z1"]["level_cm"])
        SensorNode.objects.filter(pk=self.z1.pk).update(sensor_height_cm=200)
        self.assertEqual(self.zones()["z1"]["level_cm"], 50.0)
        save_reading(self.z1, 250.0, False)
        self.assertEqual(self.zones()["z1"]["level_cm"], 0.0)

    def test_alerts_cover_public_nodes_only(self):
        save_reading(self.z1, 20.0, True)
        Alert.objects.create(node=self.z2, distance_cm=10, threshold_cm=30)
        alerts = build_snapshot()["alerts"]
        self.assertEqual(len(alerts), 1)
        self.assertEqual((alerts[0]["zone_key"], alerts[0]["severity"], alerts[0]["ended_at"]),
                         ("z1", "alert", None))
        self.assertTrue(alerts[0]["id"].startswith("alert-"))
        save_reading(self.z1, 80.0, False)
        self.assertIsNotNone(build_snapshot()["alerts"][0]["ended_at"])

    def test_old_resolved_alerts_are_left_out(self):
        old = timezone.now() - timedelta(days=45)
        Alert.objects.create(node=self.z1, distance_cm=10, threshold_cm=30,
                             status=Alert.Status.RESOLVED, created_at=old, resolved_at=old)
        self.assertEqual(build_snapshot()["alerts"], [])

    def test_only_published_active_announcements_are_sent_and_trimmed(self):
        Announcement.objects.create(title="Private", body="x", publish_to_public=False)
        Announcement.objects.create(title="Hidden", body="x", publish_to_public=True, is_active=False)
        Announcement.objects.create(title="T" * 150, body="B" * 3000, publish_to_public=True)
        notes = build_snapshot()["announcements"]
        self.assertEqual(len(notes), 1)
        self.assertEqual((len(notes[0]["title"]), len(notes[0]["body"])), (120, 2000))
        self.assertTrue(notes[0]["active"])

    def test_envelope_asks_the_public_site_to_replace_and_has_a_timezone(self):
        snapshot = build_snapshot()
        self.assertEqual(snapshot["schema"], 1)
        self.assertEqual(snapshot["replace"], ["zones", "announcements"])
        self.assertRegex(snapshot["sent_at"], r"[+-]\d{2}:\d{2}$")

    def test_no_private_data_is_ever_sent(self):
        Resident.objects.create(full_name="Maria Santos", phone_number="639170000001",
                                address="Purok 7 hidden street", node=self.z1)
        SMSLog.objects.create(phone_number="639170000001", body="secret sms body")
        save_reading(self.z1, 20.0, True)
        text = json.dumps(build_snapshot())
        for secret in ("Maria", "639170000001", "hidden street", "secret mill", "secret sms body"):
            self.assertNotIn(secret, text)


class ConfigTests(TestCase):
    def test_config_problems_are_explained(self):
        base = dict(PUBLIC_PUBLISH_ENABLED=True, PUBLIC_SITE_URL="https://example.org", PUBLIC_SITE_TOKEN="t")
        cases = [
            (dict(base, PUBLIC_PUBLISH_ENABLED=False), "switched off"),
            (dict(base, PUBLIC_SITE_URL=""), "PUBLIC_SITE_URL is missing"),
            (dict(base, PUBLIC_SITE_URL="http://example.org"), "https://"),
            (dict(base, PUBLIC_SITE_TOKEN=""), "PUBLIC_SITE_TOKEN"),
        ]
        for values, expected in cases:
            with override_settings(**values):
                self.assertIn(expected, config_problem())
        with override_settings(**dict(base, PUBLIC_SITE_URL="http://127.0.0.1:8001")):
            self.assertEqual(config_problem(), "")
        with override_settings(**base):
            self.assertEqual(config_problem(), "")


@override_settings(SMS_ASYNC=False, **PUBLISH_ON)
class PublishTests(TestCase):
    def setUp(self):
        SensorNode.objects.create(node_id="Z1", name="Zone 1", is_public=True, last_seen=timezone.now())

    def test_success_sends_the_snapshot_and_records_status(self):
        calls = []
        self.assertTrue(publish_once(sender=lambda payload, url, token: calls.append((payload, url, token))))
        payload, url, token = calls[0]
        self.assertEqual(url, "https://example.org/api/ingest/")
        self.assertEqual(token, "secret-token-value")
        self.assertEqual(payload["schema"], 1)
        status = PublishStatus.load()
        self.assertIsNotNone(status.last_success_at)
        self.assertEqual(status.failures_in_a_row, 0)

    def test_failures_are_counted_then_cleared(self):
        def broken(payload, url, token):
            raise PublishError("HTTP 503 from the public site")

        self.assertFalse(publish_once(sender=broken))
        self.assertFalse(publish_once(sender=broken))
        status = PublishStatus.load()
        self.assertEqual(status.failures_in_a_row, 2)
        self.assertIn("503", status.last_error)
        self.assertIsNone(status.last_success_at)
        self.assertTrue(publish_once(sender=lambda payload, url, token: None))
        status = PublishStatus.load()
        self.assertEqual((status.failures_in_a_row, status.last_error), (0, ""))

    @override_settings(PUBLIC_SITE_TOKEN="")
    def test_missing_config_fails_without_sending(self):
        sent = []
        self.assertFalse(publish_once(sender=lambda *args: sent.append(args)))
        self.assertEqual(sent, [])
        self.assertIn("PUBLIC_SITE_TOKEN", PublishStatus.load().last_error)


class SendTests(TestCase):
    URL = "https://example.org/api/ingest/"

    def test_request_has_bearer_token_json_and_url(self):
        response = MagicMock()
        response.__enter__.return_value.status = 200
        with patch("monitor.publisher.urllib.request.urlopen", return_value=response) as urlopen:
            send({"schema": 1}, self.URL, "tok")
        request = urlopen.call_args[0][0]
        self.assertEqual(request.full_url, self.URL)
        self.assertEqual(request.get_header("Authorization"), "Bearer tok")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(request.data), {"schema": 1})

    def test_errors_become_publish_errors_without_leaking_the_token(self):
        http_error = urllib.error.HTTPError(self.URL, 401, "Unauthorized", {}, io.BytesIO(b"{}"))
        for failure in (http_error, urllib.error.URLError("no route")):
            with patch("monitor.publisher.urllib.request.urlopen", side_effect=failure):
                with self.assertRaises(PublishError) as caught:
                    send({}, self.URL, "tok-123")
            self.assertNotIn("tok-123", str(caught.exception))
        self.assertIn("401", str(PublishError("HTTP 401 from the public site")))


class CommandTests(TestCase):
    @override_settings(PUBLIC_PUBLISH_ENABLED=False)
    def test_refuses_to_start_when_not_configured(self):
        with self.assertRaises(CommandError):
            call_command("publish_public", "--once", stdout=io.StringIO())

    @override_settings(**PUBLISH_ON)
    def test_once_sends_and_reports(self):
        out = io.StringIO()
        with patch("monitor.management.commands.publish_public.publish_once", return_value=True):
            call_command("publish_public", "--once", stdout=out)
        self.assertIn("sent", out.getvalue())