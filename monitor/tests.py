from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token

from .models import Alert, AlertThreshold, SensorNode
from .services import save_reading


class ThresholdTests(TestCase):
    def setUp(self):
        self.node = SensorNode.objects.create(node_id="Z1", name="Test Zone")
        AlertThreshold.objects.create(node=self.node, alert_distance_cm=30)

    def test_both_sensors_agree_creates_alert(self):
        save_reading(self.node, 20.0, True)
        self.assertEqual(Alert.objects.filter(status="ACTIVE").count(), 1)

    def test_ultrasonic_only_does_not_alert(self):
        save_reading(self.node, 20.0, False)
        self.assertEqual(Alert.objects.count(), 0)

    def test_float_only_does_not_alert(self):
        save_reading(self.node, 80.0, True)
        self.assertEqual(Alert.objects.count(), 0)

    def test_no_echo_does_not_alert(self):
        save_reading(self.node, None, True)
        self.assertEqual(Alert.objects.count(), 0)

    def test_exactly_at_threshold_alerts(self):
        save_reading(self.node, 30.0, True)
        self.assertEqual(Alert.objects.count(), 1)

    def test_no_duplicate_active_alert(self):
        save_reading(self.node, 20.0, True)
        save_reading(self.node, 18.0, True)
        self.assertEqual(Alert.objects.count(), 1)

    def test_alert_resolves_only_when_both_clear(self):
        save_reading(self.node, 20.0, True)
        save_reading(self.node, 80.0, True)   # sensors disagree: stays active
        self.assertEqual(Alert.objects.filter(status="ACTIVE").count(), 1)
        save_reading(self.node, None, False)  # no echo: stays active
        self.assertEqual(Alert.objects.filter(status="ACTIVE").count(), 1)
        save_reading(self.node, 80.0, False)  # both clear: resolves
        self.assertEqual(Alert.objects.filter(status="ACTIVE").count(), 0)
        self.assertEqual(Alert.objects.filter(status="RESOLVED").count(), 1)

    def test_new_alert_after_resolve(self):
        save_reading(self.node, 20.0, True)
        save_reading(self.node, 80.0, False)
        save_reading(self.node, 20.0, True)
        self.assertEqual(Alert.objects.count(), 2)
        self.assertEqual(Alert.objects.filter(status="ACTIVE").count(), 1)

    def test_inactive_threshold_does_not_alert(self):
        AlertThreshold.objects.update(is_active=False)
        save_reading(self.node, 10.0, True)
        self.assertEqual(Alert.objects.count(), 0)

    def test_node_without_threshold_does_not_alert(self):
        other = SensorNode.objects.create(node_id="Z2", name="No threshold")
        save_reading(other, 10.0, True)
        self.assertEqual(Alert.objects.count(), 0)


class ApiAlertTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user("official", password="x-pass-123")
        self.token = Token.objects.create(user=user)
        self.node = SensorNode.objects.create(node_id="Z1", name="Test Zone")
        AlertThreshold.objects.create(node=self.node, alert_distance_cm=30)

    def test_post_reading_creates_alert_and_api_lists_it(self):
        headers = {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}
        response = self.client.post(
            reverse("api-readings"),
            {"node": "Z1", "distance_cm": 25, "float_triggered": True},
            content_type="application/json",
            **headers,
        )
        self.assertEqual(response.status_code, 201)
        alerts = self.client.get(reverse("api-alerts") + "?status=active", **headers)
        self.assertEqual(alerts.json()["count"], 1)
        self.assertEqual(alerts.json()["results"][0]["node"], "Z1")

    def test_alerts_require_authentication(self):
        self.assertEqual(self.client.get(reverse("api-alerts")).status_code, 401)