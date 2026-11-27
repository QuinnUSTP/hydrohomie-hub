from rest_framework import serializers

from .models import Alert, SensorNode, SensorReading

# The HC-SR04 range is roughly 2-400 cm. Check your module's datasheet.
MAX_DISTANCE_CM = 500


class SensorNodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SensorNode
        fields = ["node_id", "name", "location", "is_active", "last_seen"]
        read_only_fields = fields


class SensorReadingSerializer(serializers.ModelSerializer):
    node = serializers.SlugRelatedField(
        slug_field="node_id", queryset=SensorNode.objects.all()
    )

    class Meta:
        model = SensorReading
        fields = ["id", "node", "distance_cm", "float_triggered", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_node(self, node):
        if not node.is_active:
            raise serializers.ValidationError("This node is not active.")
        return node

    def validate_distance_cm(self, value):
        if value is not None and not 0 <= value <= MAX_DISTANCE_CM:
            raise serializers.ValidationError(
                f"Distance must be between 0 and {MAX_DISTANCE_CM} cm."
            )
        return value


class AlertSerializer(serializers.ModelSerializer):
    node = serializers.SlugRelatedField(slug_field="node_id", read_only=True)
    node_name = serializers.CharField(source="node.name", read_only=True)

    class Meta:
        model = Alert
        fields = [
            "id",
            "node",
            "node_name",
            "distance_cm",
            "threshold_cm",
            "status",
            "created_at",
            "resolved_at",
        ]
        read_only_fields = fields