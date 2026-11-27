from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import PublishStatus, SensorNode

PUBLISH_ON = dict(PUBLIC_PUBLISH_ENABLED=True, PUBLIC_SITE_URL="https://example.org",
                  PUBLIC_SITE_TOKEN="secret-token-value")


class PublicSitePageTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_user("official", password="x-pass-123")
        self.node = SensorNode.objects.create(node_id="Z1", name="Zone 1")

    def login(self):
        self.client.login(username="official", password="x-pass-123")

    def test_everything_requires_login(self):
        urls = [reverse("public-site"), reverse("public-site-zone", args=[self.node.pk])]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302, url)
        self.assertEqual(self.client.post(reverse("public-site-send")).status_code, 302)

    def test_page_explains_problems_and_never_shows_the_token(self):
        self.login()
        with override_settings(PUBLIC_PUBLISH_ENABLED=False, PUBLIC_SITE_URL="", PUBLIC_SITE_TOKEN=""):
            response = self.client.get(reverse("public-site"))
        self.assertContains(response, "switched off")
        self.assertContains(response, "Not running")
        with override_settings(**PUBLISH_ON):
            response = self.client.get(reverse("public-site"))
        self.assertContains(response, "Configured")
        self.assertContains(response, "https://example.org")
        self.assertNotContains(response, "secret-token-value")

    def test_publisher_counts_as_running_after_a_recent_attempt(self):
        self.login()
        status = PublishStatus.load()
        status.last_attempt_at = timezone.now()
        status.last_success_at = timezone.now()
        status.save()
        response = self.client.get(reverse("public-site"))
        self.assertContains(response, "Running")
        self.assertContains(response, "OK")

    def test_send_now_reports_success(self):
        self.login()
        with patch("monitor.pages.publish_once", return_value=True):
            response = self.client.post(reverse("public-site-send"), follow=True)
        self.assertContains(response, "Sent to the public site.")

    def test_send_now_reports_failure_in_red(self):
        self.login()
        status = PublishStatus.load()
        status.last_error = "HTTP 503 from the public site"
        status.save()
        with patch("monitor.pages.publish_once", return_value=False):
            response = self.client.post(reverse("public-site-send"), follow=True)
        self.assertContains(response, "Could not send: HTTP 503")
        self.assertContains(response, "alert-danger")

    def test_send_only_accepts_post(self):
        self.login()
        self.assertEqual(self.client.get(reverse("public-site-send")).status_code, 405)

    def test_zone_settings_can_be_saved(self):
        self.login()
        response = self.client.post(reverse("public-site-zone", args=[self.node.pk]),
                                    {"is_public": "on", "public_name": "Riverside", "sensor_height_cm": "200"})
        self.assertRedirects(response, reverse("public-site"))
        self.node.refresh_from_db()
        self.assertTrue(self.node.is_public)
        self.assertEqual(self.node.public_name, "Riverside")
        self.assertEqual(self.node.sensor_height_cm, 200)

    def test_negative_sensor_height_is_rejected(self):
        self.login()
        response = self.client.post(reverse("public-site-zone", args=[self.node.pk]),
                                    {"is_public": "on", "sensor_height_cm": "-5"})
        self.assertEqual(response.status_code, 200)
        self.node.refresh_from_db()
        self.assertFalse(self.node.is_public)

    def test_navbar_links_to_the_page(self):
        self.login()
        response = self.client.get(reverse("public-site"))
        self.assertContains(response, 'href="%s"' % reverse("public-site"))