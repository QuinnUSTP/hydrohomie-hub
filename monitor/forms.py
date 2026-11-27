from django import forms

from .models import AlertThreshold, Announcement, Resident, SensorNode


class BootstrapFormMixin:
    """Add Bootstrap CSS classes to every form field."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "form-check-input"
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = "form-select"
            else:
                widget.attrs["class"] = "form-control"


class ThresholdForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = AlertThreshold
        fields = ["node", "alert_distance_cm", "cooldown_minutes", "is_active"]


class AnnouncementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ["title", "body", "is_active", "publish_to_public"]
        widgets = {"body": forms.Textarea(attrs={"rows": 4})}


class ResidentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Resident
        fields = ["full_name", "phone_number", "address", "node", "receives_sms"]

class NodePublicForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = SensorNode
        fields = ["is_public", "public_name", "sensor_height_cm"]