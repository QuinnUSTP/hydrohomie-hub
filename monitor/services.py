from django.db import transaction

from .models import Alert, AlertThreshold, SensorReading
from .sms import dispatch_alert_sms


def evaluate_alert(reading):
    """Plain-code threshold check. No AI is involved.

    An alert is created only when BOTH sensors agree:
      - the ultrasonic distance is at or below the node's threshold, AND
      - the float switch is triggered.

    An active alert is resolved only when BOTH sensors clearly say the water
    is low: distance above the threshold AND float not triggered. If the
    sensors disagree, or the ultrasonic gave no echo, the alert stays as it is.

    Returns the newly created Alert, or None if no new alert was created.
    """
    node = reading.node
    threshold = AlertThreshold.objects.filter(node=node, is_active=True).first()
    if threshold is None:
        return None

    distance = reading.distance_cm
    limit = threshold.alert_distance_cm
    ultrasonic_high = distance is not None and distance <= limit
    both_agree = ultrasonic_high and reading.float_triggered

    active = Alert.objects.filter(node=node, status=Alert.Status.ACTIVE).first()

    if both_agree:
        if active is not None:
            return None
        return Alert.objects.create(
            node=node,
            reading=reading,
            distance_cm=distance,
            threshold_cm=limit,
            created_at=reading.created_at,
        )

    clearly_low = distance is not None and distance > limit and not reading.float_triggered
    if clearly_low and active is not None:
        active.status = Alert.Status.RESOLVED
        active.resolved_at = reading.created_at
        active.save(update_fields=["status", "resolved_at"])
    return None


def save_reading(node, distance_cm, float_triggered):
    """Save one reading, update last_seen, then run the threshold check.

    Used by the REST API and by the serial bridge.
    """
    with transaction.atomic():
        reading = SensorReading.objects.create(
            node=node,
            distance_cm=distance_cm,
            float_triggered=float_triggered,
        )
        node.last_seen = reading.created_at
        node.save(update_fields=["last_seen"])
        new_alert = evaluate_alert(reading)

    # After the database commit, so the SMS job always sees the saved alert.
    if new_alert is not None:
        dispatch_alert_sms(new_alert)
    return reading