from django.urls import path

from . import views

urlpatterns = [
    path("nodes/", views.NodeListView.as_view(), name="api-nodes"),
    path("readings/", views.ReadingListCreateView.as_view(), name="api-readings"),
    path("alerts/", views.AlertListView.as_view(), name="api-alerts"),
    path("status/", views.StatusView.as_view(), name="api-status"),
]