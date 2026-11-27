import json
import logging
import re
import urllib.error
import urllib.request
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import Alert, AlertThreshold, Announcement, PublishStatus, SensorNode

logger = logging.getLogger(__name__)

OFFLINE_AFTER = timedelta(seconds=120)
ALERT_HISTORY = timedelta(days=30)
MAX_ZONES, MAX_ALERTS, MAX_NOTES = 50, 200, 50
HINTS = {400: "payload rejected", 401: "token rejected, check PUBLIC_SITE_TOKEN",
         403: "ingest is disabled on the public site, set INGEST_TOKEN there",
         413: "payload too large"}


class PublishError(Exception):
    pass


def endpoint():
    return settings.PUBLIC_SITE_URL.rstrip("/") + "/api/ingest/"


def config_problem():
    if not settings.PUBLIC_PUBLISH_ENABLED:
        return "Publishing is switched off. Set PUBLIC_PUBLISH_ENABLED=True in .env."
    url = settings.PUBLIC_SITE_URL
    if not url:
        return "PUBLIC_SITE_URL is missing in .env."
    parsed = urlparse(url)
    local = parsed.hostname in ("localhost", "127.0.0.1")
    if not parsed.hostname or not (parsed.scheme == "https" or (parsed.scheme == "http" and local)):
        return "PUBLIC_SITE_URL must be a full address starting with https://."
    if not settings.PUBLIC_SITE_TOKEN:
        return "PUBLIC_SITE_TOKEN is missing in .env."
    return ""


def _iso(value):
    return timezone.localtime(value).isoformat(timespec="seconds")


def _zone_keys(nodes):
    keys, used = {}, set()
    for node in nodes:
        key = re.sub(r"[^a-z0-9]+", "-", node.node_id.lower()).strip("-")[:40].strip("-")
        if not key or key in used:
            key = f"{key[:30]}-{node.pk}".strip("-")
        used.add(key)
        keys[node.pk] = key
    return keys


def _zone_state(node, latest, threshold, has_active_alert, now):
    if has_active_alert:
        return "alert"
    if node.last_seen is None or now - node.last_seen > OFFLINE_AFTER:
        return "offline"
    if latest is None:
        return "unknown"
    ultrasonic_high = (latest.distance_cm is not None and threshold is not None
                       and latest.distance_cm <= threshold.alert_distance_cm)
    return "watch" if ultrasonic_high or latest.float_triggered else "normal"


def _level(node, latest):
    if node.sensor_height_cm is None or latest is None or latest.distance_cm is None:
        return None
    return round(min(1000.0, max(0.0, node.sensor_height_cm - latest.distance_cm)), 1)


def build_snapshot(now=None):
    now = now or timezone.now()
    nodes = list(SensorNode.objects.filter(is_active=True, is_public=True).order_by("node_id")[:MAX_ZONES])
    keys = _zone_keys(nodes)
    thresholds = {t.node_id: t for t in AlertThreshold.objects.filter(is_active=True, node__in=nodes)}
    active_ids = set(Alert.objects.filter(status=Alert.Status.ACTIVE, node__in=nodes)
                     .values_list("node_id", flat=True))

    def name_of(node):
        return (node.public_name or node.name)[:80]

    zones = []
    for node in nodes:
        latest = node.readings.first()
        zones.append({
            "key": keys[node.pk],
            "name": name_of(node),
            "state": _zone_state(node, latest, thresholds.get(node.pk), node.pk in active_ids, now),
            "level_cm": _level(node, latest),
            "measured_at": _iso(latest.created_at if latest else node.created_at),
        })

    by_pk = {n.pk: n for n in nodes}
    since = now - ALERT_HISTORY
    alert_rows = (Alert.objects.filter(node__in=nodes)
                  .filter(Q(status=Alert.Status.ACTIVE) | Q(created_at__gte=since))
                  .order_by("-created_at")[:MAX_ALERTS])
    alerts = [{
        "id": f"alert-{a.pk}",
        "zone_key": keys[a.node_id],
        "zone_name": name_of(by_pk[a.node_id]),
        "severity": "alert",
        "started_at": _iso(a.created_at),
        "ended_at": _iso(a.resolved_at) if a.resolved_at else None,
        "summary": "Sensors in this zone detected high water.",
    } for a in alert_rows]

    notes = Announcement.objects.filter(publish_to_public=True, is_active=True).order_by("-created_at")[:MAX_NOTES]
    announcements = [{
        "id": f"note-{n.pk}",
        "title": n.title[:120],
        "body": n.body[:2000],
        "published_at": _iso(n.created_at),
        "active": True,
    } for n in notes]

    return {"schema": 1, "sent_at": _iso(now), "replace": ["zones", "announcements"],
            "zones": zones, "alerts": alerts, "announcements": announcements}


def send(payload, url, token, timeout=10):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}",
                 "User-Agent": "HydroHomie-Hub/1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise PublishError(f"Unexpected HTTP {response.status} from the public site")
    except urllib.error.HTTPError as exc:
        detail = HINTS.get(exc.code, "unexpected answer")
        extra = ""
        if exc.code == 400:
            extra = " " + exc.read(300).decode("utf-8", "ignore")
        raise PublishError(f"HTTP {exc.code} from the public site ({detail}).{extra}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise PublishError(f"Cannot reach the public site: {exc}") from None


def publish_once(now=None, sender=send):
    now = now or timezone.now()
    status = PublishStatus.load()
    status.last_attempt_at = now
    try:
        problem = config_problem()
        if problem:
            raise PublishError(problem)
        sender(build_snapshot(now), endpoint(), settings.PUBLIC_SITE_TOKEN)
    except PublishError as exc:
        status.failures_in_a_row += 1
        status.last_error = str(exc)[:500]
        status.save()
        logger.warning("Public publish failed: %s", exc)
        return False
    status.last_success_at = now
    status.failures_in_a_row = 0
    status.last_error = ""
    status.save()
    return True