from django.contrib import admin

from .models import (
    Alert,
    AlertThreshold,
    Announcement,
    KeywordResponse,
    Resident,
    SensorNode,
    SensorReading,
    SMSLog,
)


@admin.register(SensorNode)
class SensorNodeAdmin(admin.ModelAdmin):
    list_display = ("node_id", "name", "location", "is_active", "last_seen")
    list_filter = ("is_active",)
    search_fields = ("node_id", "name", "location")


@admin.register(SensorReading)
class SensorReadingAdmin(admin.ModelAdmin):
    list_display = ("node", "distance_cm", "float_triggered", "created_at")
    list_filter = ("node", "float_triggered")
    date_hierarchy = "created_at"


@admin.register(AlertThreshold)
class AlertThresholdAdmin(admin.ModelAdmin):
    list_display = ("node", "alert_distance_cm", "cooldown_minutes", "is_active")
    list_filter = ("is_active",)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = (
        "node",
        "status",
        "distance_cm",
        "threshold_cm",
        "created_at",
        "resolved_at",
    )
    list_filter = ("status", "node")
    date_hierarchy = "created_at"


@admin.register(Resident)
class ResidentAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone_number", "node", "receives_sms")
    list_filter = ("node", "receives_sms")
    search_fields = ("full_name", "phone_number", "address")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "created_by", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title", "body")


@admin.register(SMSLog)
class SMSLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "direction", "phone_number", "status", "resident")
    list_filter = ("direction", "status")
    search_fields = ("phone_number", "body", "provider_sid")


@admin.register(KeywordResponse)
class KeywordResponseAdmin(admin.ModelAdmin):
    list_display = ("keyword", "is_active")
    list_filter = ("is_active",)