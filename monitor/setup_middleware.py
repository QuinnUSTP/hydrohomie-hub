from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import redirect

ALLOWED_PREFIXES = ("/setup/", "/static/")


class FirstRunSetupMiddleware:
    """Until an administrator exists, send every page to the setup screen."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (getattr(settings, "FIRST_RUN_SETUP", False)
                and not request.path.startswith(ALLOWED_PREFIXES)
                and not get_user_model().objects.exists()):
            return redirect("setup")
        return self.get_response(request)