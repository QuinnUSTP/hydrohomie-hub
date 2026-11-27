from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.http import HttpResponse
from django.urls import reverse_lazy

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import redirect
from django.utils import timezone
from django.views import View

from .forms import NodePublicForm
from .models import Announcement, PublishStatus, SensorNode

from .publisher import config_problem, publish_once
from django.views.generic import (
    CreateView,
    DeleteView,
    ListView,
    TemplateView,
    UpdateView,
)

from .forms import AnnouncementForm, ResidentForm, ThresholdForm
from .models import AlertThreshold, Announcement, Resident, SMSLog


def robots_txt(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")


class MonitoringView(LoginRequiredMixin, TemplateView):
    template_name = "monitor/monitoring.html"


# ---------- Thresholds ----------
class ThresholdListView(LoginRequiredMixin, ListView):
    model = AlertThreshold
    template_name = "monitor/threshold_list.html"
    context_object_name = "thresholds"

    def get_queryset(self):
        return AlertThreshold.objects.select_related("node").order_by("node__node_id")


class ThresholdCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    form_class = ThresholdForm
    template_name = "monitor/form.html"
    success_url = reverse_lazy("thresholds")
    success_message = "Threshold saved."
    extra_context = {"page_title": "Add threshold", "back_url": reverse_lazy("thresholds")}


class ThresholdUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = AlertThreshold
    form_class = ThresholdForm
    template_name = "monitor/form.html"
    success_url = reverse_lazy("thresholds")
    success_message = "Threshold updated."
    extra_context = {"page_title": "Edit threshold", "back_url": reverse_lazy("thresholds")}


# ---------- Announcements ----------
class AnnouncementListView(LoginRequiredMixin, ListView):
    model = Announcement
    template_name = "monitor/announcement_list.html"
    context_object_name = "announcements"
    paginate_by = 20

    def get_queryset(self):
        return Announcement.objects.select_related("created_by")


class AnnouncementCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    form_class = AnnouncementForm
    template_name = "monitor/form.html"
    success_url = reverse_lazy("announcements")
    success_message = "Announcement saved."
    extra_context = {
        "page_title": "New announcement",
        "back_url": reverse_lazy("announcements"),
    }

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class AnnouncementUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Announcement
    form_class = AnnouncementForm
    template_name = "monitor/form.html"
    success_url = reverse_lazy("announcements")
    success_message = "Announcement updated."
    extra_context = {
        "page_title": "Edit announcement",
        "back_url": reverse_lazy("announcements"),
    }


class AnnouncementDeleteView(LoginRequiredMixin, DeleteView):
    model = Announcement
    template_name = "monitor/confirm_delete.html"
    success_url = reverse_lazy("announcements")
    extra_context = {"back_url": reverse_lazy("announcements")}


# ---------- Residents ----------
class ResidentListView(LoginRequiredMixin, ListView):
    model = Resident
    template_name = "monitor/resident_list.html"
    context_object_name = "residents"
    paginate_by = 25

    def get_queryset(self):
        queryset = Resident.objects.select_related("node")
        self.q = self.request.GET.get("q", "").strip()
        if self.q:
            queryset = queryset.filter(
                Q(full_name__icontains=self.q)
                | Q(phone_number__icontains=self.q)
                | Q(address__icontains=self.q)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.q
        return context


class ResidentCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    form_class = ResidentForm
    template_name = "monitor/form.html"
    success_url = reverse_lazy("residents")
    success_message = "Resident added."
    extra_context = {"page_title": "Add resident", "back_url": reverse_lazy("residents")}


class ResidentUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Resident
    form_class = ResidentForm
    template_name = "monitor/form.html"
    success_url = reverse_lazy("residents")
    success_message = "Resident updated."
    extra_context = {"page_title": "Edit resident", "back_url": reverse_lazy("residents")}


class ResidentDeleteView(LoginRequiredMixin, DeleteView):
    model = Resident
    template_name = "monitor/confirm_delete.html"
    success_url = reverse_lazy("residents")
    extra_context = {"back_url": reverse_lazy("residents")}


# ---------- SMS log ----------
class SMSLogListView(LoginRequiredMixin, ListView):
    model = SMSLog
    template_name = "monitor/smslog_list.html"
    context_object_name = "logs"
    paginate_by = 50

    def get_queryset(self):
        return SMSLog.objects.select_related("resident")

class PublicSiteView(LoginRequiredMixin, TemplateView):
    template_name = "monitor/public_site.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status = PublishStatus.load()
        now = timezone.now()
        interval = max(10, settings.PUBLIC_PUBLISH_INTERVAL)
        window = max(interval, 60) * 3 + 10
        running = (status.last_attempt_at is not None
                   and now - status.last_attempt_at <= timedelta(seconds=window))
        if status.last_success_at is None:
            health = "never"
        elif now - status.last_success_at <= timedelta(seconds=120):
            health = "ok"
        else:
            health = "stale"
        context.update({
            "problem": config_problem(),
            "site_url": settings.PUBLIC_SITE_URL,
            "token_set": bool(settings.PUBLIC_SITE_TOKEN),
            "status": status,
            "publisher_running": running,
            "health": health,
            "nodes": SensorNode.objects.filter(is_active=True).order_by("node_id"),
            "public_notes": Announcement.objects.filter(publish_to_public=True, is_active=True).count(),
        })
        return context


class PublicSiteSendView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        if publish_once():
            messages.success(request, "Sent to the public site.")
        else:
            messages.error(request, f"Could not send: {PublishStatus.load().last_error}")
        return redirect("public-site")


class NodePublicUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = SensorNode
    form_class = NodePublicForm
    template_name = "monitor/form.html"
    success_url = reverse_lazy("public-site")
    success_message = "Zone settings saved."
    extra_context = {"page_title": "Public settings for a zone", "back_url": reverse_lazy("public-site")}