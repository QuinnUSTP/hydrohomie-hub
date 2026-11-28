from django.urls import path
from django.views.generic import RedirectView

from . import pages

urlpatterns = [
    path("", RedirectView.as_view(url="/dashboard/")),
    path("robots.txt", pages.robots_txt, name="robots"),
    path("dashboard/", pages.MonitoringView.as_view(), name="dashboard"),
    path("dashboard/thresholds/", pages.ThresholdListView.as_view(), name="thresholds"),
    path("dashboard/thresholds/add/", pages.ThresholdCreateView.as_view(), name="threshold-add"),
    path("dashboard/thresholds/<int:pk>/edit/", pages.ThresholdUpdateView.as_view(), name="threshold-edit"),
    path("dashboard/announcements/", pages.AnnouncementListView.as_view(), name="announcements"),
    path("dashboard/announcements/add/", pages.AnnouncementCreateView.as_view(), name="announcement-add"),
    path("dashboard/announcements/<int:pk>/edit/", pages.AnnouncementUpdateView.as_view(), name="announcement-edit"),
    path("dashboard/announcements/<int:pk>/delete/", pages.AnnouncementDeleteView.as_view(), name="announcement-delete"),
    path("dashboard/residents/", pages.ResidentListView.as_view(), name="residents"),
    path("dashboard/residents/add/", pages.ResidentCreateView.as_view(), name="resident-add"),
    path("dashboard/residents/<int:pk>/edit/", pages.ResidentUpdateView.as_view(), name="resident-edit"),
    path("dashboard/residents/<int:pk>/delete/", pages.ResidentDeleteView.as_view(), name="resident-delete"),
    path("dashboard/sms-log/", pages.SMSLogListView.as_view(), name="sms-log"),
    path("dashboard/public-site/", pages.PublicSiteView.as_view(), name="public-site"),
    path("dashboard/public-site/send/", pages.PublicSiteSendView.as_view(), name="public-site-send"),
    path("dashboard/public-site/zones/<int:pk>/", pages.NodePublicUpdateView.as_view(), name="public-site-zone"),
    path("setup/", pages.SetupView.as_view(), name="setup"),
    path("dashboard/nodes/", pages.NodeListView.as_view(), name="nodes"),
    path("dashboard/nodes/add/", pages.NodeCreateView.as_view(), name="node-add"),
    path("dashboard/nodes/<int:pk>/edit/", pages.NodeUpdateView.as_view(), name="node-edit"),
]