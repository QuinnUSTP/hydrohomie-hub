from datetime import timedelta

from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Alert, AlertThreshold, SensorNode, SensorReading
from .serializers import (
    AlertSerializer,
    SensorNodeSerializer,
    SensorReadingSerializer,
)
from .services import save_reading

# A node counts as offline if it has not been heard from for this long.
OFFLINE_AFTER = timedelta(seconds=120)
RECENT_READINGS = 10


class NodeListView(generics.ListAPIView):
    queryset = SensorNode.objects.all()
    serializer_class = SensorNodeSerializer


class ReadingListCreateView(generics.ListCreateAPIView):
    serializer_class = SensorReadingSerializer

    def get_queryset(self):
        queryset = SensorReading.objects.select_related("node")
        node_id = self.request.query_params.get("node")
        if node_id:
            queryset = queryset.filter(node__node_id=node_id)
        return queryset

    def perform_create(self, serializer):
        data = serializer.validated_data
        serializer.instance = save_reading(
            node=data["node"],
            distance_cm=data.get("distance_cm"),
            float_triggered=data.get("float_triggered", False),
        )


class AlertListView(generics.ListAPIView):
    serializer_class = AlertSerializer

    def get_queryset(self):
        queryset = Alert.objects.select_related("node")
        status = self.request.query_params.get("status", "").upper()
        if status in (Alert.Status.ACTIVE, Alert.Status.RESOLVED):
            queryset = queryset.filter(status=status)
        return queryset


class StatusView(APIView):
    """One request that gives the dashboard everything it needs to redraw."""

    def get(self, request):
        now = timezone.now()
        active_alerts = {
            alert.node_id: alert
            for alert in Alert.objects.filter(status=Alert.Status.ACTIVE)
        }
        thresholds = {
            t.node_id: t for t in AlertThreshold.objects.filter(is_active=True)
        }

        nodes = []
        for node in SensorNode.objects.filter(is_active=True):
            recent = list(node.readings.all()[:RECENT_READINGS])
            latest = recent[0] if recent else None
            online = node.last_seen is not None and now - node.last_seen <= OFFLINE_AFTER
            alert = active_alerts.get(node.id)
            threshold = thresholds.get(node.id)

            ultrasonic_high = (
                latest is not None
                and latest.distance_cm is not None
                and threshold is not None
                and latest.distance_cm <= threshold.alert_distance_cm
            )
            float_high = latest is not None and latest.float_triggered

            if alert is not None:
                state = "alert"
            elif not online:
                state = "offline"
            elif ultrasonic_high or float_high:
                state = "check"
            else:
                state = "normal"

            nodes.append(
                {
                    "node_id": node.node_id,
                    "name": node.name,
                    "location": node.location,
                    "state": state,
                    "online": online,
                    "last_seen": node.last_seen,
                    "distance_cm": latest.distance_cm if latest else None,
                    "float_triggered": latest.float_triggered if latest else None,
                    "alert_distance_cm": threshold.alert_distance_cm if threshold else None,
                    "alert_since": alert.created_at if alert else None,
                    "recent": [
                        {
                            "time": r.created_at,
                            "distance_cm": r.distance_cm,
                            "float_triggered": r.float_triggered,
                        }
                        for r in recent
                    ],
                }
            )

        return Response({"server_time": now, "nodes": nodes})