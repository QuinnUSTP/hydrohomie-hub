from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Alert, AlertThreshold, Announcement, Resident, SensorNode
from .services import save_reading

PAGE_NAMES = [
    "dashboard",
    "thresholds",
    "threshold-add",
    "announcements",
    "announcement-add",
    "residents",
    "resident-add",
    "sms-log",
]


class PageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("official", password="x-pass-123")
        self.node = SensorNode.objects.create(node_id="Z1", name="Test Zone")
        self.threshold = AlertThreshold.objects.create(node=self.node, alert_distance_cm=30)

    def login(self):
        self.client.login(username="official", password="x-pass-123")

    def test_pages_require_login(self):
        for name in PAGE_NAMES:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn("/accounts/login/", response["Location"], name)

    def test_pages_load_when_logged_in(self):
        self.login()
        for name in PAGE_NAMES:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)

    def test_noindex_header_and_meta(self):
        self.login()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
        self.assertContains(response, 'name="robots" content="noindex, nofollow"')

    def test_robots_txt_disallows_everything(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Disallow: /")

    def test_create_resident_and_search(self):
        self.login()
        response = self.client.post(
            reverse("resident-add"),
            {"full_name": "Juan Dela Cruz", "phone_number": "+639171234567",
             "address": "Purok 1", "node": self.node.pk, "receives_sms": "on"},
        )
        self.assertRedirects(response, reverse("residents"))
        self.assertEqual(Resident.objects.count(), 1)
        page = self.client.get(reverse("residents") + "?q=juan")
        self.assertContains(page, "Juan Dela Cruz")
        page = self.client.get(reverse("residents") + "?q=nobody")
        self.assertNotContains(page, "Juan Dela Cruz")

    def test_bad_phone_number_is_rejected(self):
        self.login()
        response = self.client.post(
            reverse("resident-add"),
            {"full_name": "Maria", "phone_number": "09171234567"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Resident.objects.count(), 0)

    def test_announcement_records_author(self):
        self.login()
        self.client.post(
            reverse("announcement-add"),
            {"title": "Evacuation drill", "body": "Saturday 9 AM", "is_active": "on"},
        )
        self.assertEqual(Announcement.objects.get().created_by, self.user)

    def test_edit_threshold(self):
        self.login()
        response = self.client.post(
            reverse("threshold-edit", args=[self.threshold.pk]),
            {"node": self.node.pk, "alert_distance_cm": 25,
             "cooldown_minutes": 15, "is_active": "on"},
        )
        self.assertRedirects(response, reverse("thresholds"))
        self.threshold.refresh_from_db()
        self.assertEqual(self.threshold.alert_distance_cm, 25)

    def test_delete_resident_needs_post(self):
        self.login()
        resident = Resident.objects.create(full_name="A", phone_number="+639171234567")
        self.client.get(reverse("resident-delete", args=[resident.pk]))
        self.assertEqual(Resident.objects.count(), 1)
        self.client.post(reverse("resident-delete", args=[resident.pk]))
        self.assertEqual(Resident.objects.count(), 0)


class StatusApiTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_user("official", password="x-pass-123")
        self.client.login(username="official", password="x-pass-123")
        self.node = SensorNode.objects.create(node_id="Z1", name="Test Zone")
        AlertThreshold.objects.create(node=self.node, alert_distance_cm=30)

    def state(self):
        return self.client.get(reverse("api-status")).json()["nodes"][0]["state"]

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("api-status")).status_code, 401)

    def test_never_seen_node_is_offline(self):
        self.assertEqual(self.state(), "offline")

    def test_normal(self):
        save_reading(self.node, 80.0, False)
        self.assertEqual(self.state(), "normal")

    def test_one_sensor_high_is_check_not_alert(self):
        save_reading(self.node, 20.0, False)
        self.assertEqual(self.state(), "check")
        self.assertEqual(Alert.objects.count(), 0)

    def test_both_high_is_alert(self):
        save_reading(self.node, 20.0, True)
        data = self.client.get(reverse("api-status")).json()["nodes"][0]
        self.assertEqual(data["state"], "alert")
        self.assertIsNotNone(data["alert_since"])
        self.assertEqual(len(data["recent"]), 1)

    def test_no_echo_reading_is_reported(self):
        save_reading(self.node, None, False)
        data = self.client.get(reverse("api-status")).json()["nodes"][0]
        self.assertIsNone(data["distance_cm"])
        self.assertEqual(data["state"], "normal")