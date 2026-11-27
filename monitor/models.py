from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone


class SensorNode(models.Model):
    node_id = models.CharField(
        max_length=20,
        unique=True,
        help_text="Short ID sent by the firmware, for example Z1.",
    )
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["node_id"]

    def __str__(self):
        return f"{self.node_id} - {self.name}"
    public_name = models.CharField(
        max_length=80, blank=True,
        help_text="Name shown on the public website. Leave empty to use the Name above.")
    is_public = models.BooleanField(default=False, help_text="Show this zone on the public website.")
    sensor_height_cm = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(0)],
        help_text="Distance in cm from the sensor down to the river bed (zero level). "
                  "When set, the public site shows water level = this minus the measured distance.")



class SensorReading(models.Model):
    node = models.ForeignKey(
        SensorNode, on_delete=models.CASCADE, related_name="readings"
    )
    distance_cm = models.FloatField(
        null=True,
        blank=True,
        help_text="Sensor-to-water distance. Empty if the sensor gave no valid echo.",
    )
    float_triggered = models.BooleanField(
        default=False, help_text="True when the float switch reports high water."
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["node", "-created_at"])]

    def __str__(self):
        return f"{self.node.node_id} {self.distance_cm} cm float={self.float_triggered}"


class AlertThreshold(models.Model):
    node = models.OneToOneField(
        SensorNode, on_delete=models.CASCADE, related_name="threshold"
    )
    alert_distance_cm = models.FloatField(
        validators=[MinValueValidator(0)],
        help_text="Alert when the measured distance is at or below this value (water is high).",
    )
    cooldown_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Minimum minutes between repeated alerts for the same node.",
    )
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.node.node_id}: alert at <= {self.alert_distance_cm} cm"


class Alert(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        RESOLVED = "RESOLVED", "Resolved"

    node = models.ForeignKey(
        SensorNode, on_delete=models.CASCADE, related_name="alerts"
    )
    reading = models.ForeignKey(
        SensorReading,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
        help_text="The reading that triggered the alert.",
    )
    distance_cm = models.FloatField()
    threshold_cm = models.FloatField(
        help_text="Threshold value at the moment the alert was created."
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["node"],
                condition=models.Q(status="ACTIVE"),
                name="one_active_alert_per_node",
            )
        ]

    def __str__(self):
        return f"{self.node.node_id} {self.status} at {self.created_at:%Y-%m-%d %H:%M}"


phone_validator = RegexValidator(
    regex=r"^\+[1-9]\d{7,14}$",
    message="Use international format, for example +639171234567.",
)


class Resident(models.Model):
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(
        max_length=16, unique=True, validators=[phone_validator]
    )
    address = models.CharField(max_length=250, blank=True)
    node = models.ForeignKey(
        SensorNode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="residents",
        help_text="Zone whose alerts this resident receives.",
    )
    receives_sms = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.phone_number})"


class Announcement(models.Model):
    title = models.CharField(max_length=150)
    body = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcements",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    publish_to_public = models.BooleanField(
    default=False, help_text="Show this announcement on the public website.")


class SMSLog(models.Model):
    class Direction(models.TextChoices):
        OUTBOUND = "OUT", "Outbound"
        INBOUND = "IN", "Inbound"

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        SENT = "SENT", "Sent"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed"
        RECEIVED = "RECEIVED", "Received"

    direction = models.CharField(
        max_length=3, choices=Direction.choices, default=Direction.OUTBOUND
    )
    phone_number = models.CharField(max_length=16)
    body = models.TextField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.QUEUED
    )
    provider_sid = models.CharField(
        max_length=64, blank=True, help_text="Message ID returned by the SMS provider."
    )
    error_message = models.TextField(blank=True)
    resident = models.ForeignKey(
        Resident,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sms_logs",
    )
    alert = models.ForeignKey(
        Alert,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sms_logs",
        help_text="Alert that caused this message, if any.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.direction} {self.phone_number} {self.status}"


class KeywordResponse(models.Model):
    keyword = models.CharField(
        max_length=30,
        unique=True,
        help_text="Word a resident texts in, for example STATUS. Saved in uppercase.",
    )
    response_text = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["keyword"]

    def save(self, *args, **kwargs):
        self.keyword = self.keyword.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.keyword

class PublishStatus(models.Model):
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    failures_in_a_row = models.PositiveIntegerField(default=0)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"Public site publishing, {self.failures_in_a_row} failures in a row"