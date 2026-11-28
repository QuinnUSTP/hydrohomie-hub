from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import SensorNode

User = get_user_model()
PASSWORD = "a-Strong-pass-2026"


@override_settings(FIRST_RUN_SETUP=True)
class FirstRunSetupTests(TestCase):
    def test_pages_redirect_to_setup_when_no_user_exists(self):
        response = self.client.get("/dashboard/")
        self.assertRedirects(response, reverse("setup"), fetch_redirect_response=False)

    def test_setup_creates_a_logged_in_superuser(self):
        response = self.client.post(reverse("setup"), {
            "username": "admin", "password1": PASSWORD, "password2": PASSWORD})
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        user = User.objects.get(username="admin")
        self.assertTrue(user.is_superuser and user.is_staff)

    def test_setup_is_closed_once_a_user_exists(self):
        User.objects.create_user("someone", password=PASSWORD)
        response = self.client.get(reverse("setup"))
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)


@override_settings(FIRST_RUN_SETUP=False)
class SetupOffByDefaultTests(TestCase):
    def test_normal_login_redirect_is_unchanged(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])


class NodeScreenTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user("op", password=PASSWORD))

    def test_add_edit_and_list(self):
        self.client.post(reverse("node-add"), {
            "node_id": "Z9", "name": "Test zone", "location": "River bend", "is_active": "on"})
        node = SensorNode.objects.get(node_id="Z9")
        self.client.post(reverse("node-edit", args=[node.pk]), {
            "node_id": "Z9", "name": "Renamed", "location": "", "is_active": "on"})
        node.refresh_from_db()
        self.assertEqual(node.name, "Renamed")
        self.assertContains(self.client.get(reverse("nodes")), "Renamed")

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("nodes")).status_code, 302)