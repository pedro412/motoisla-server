from rest_framework import serializers

from apps.inventory.models import InventoryMovement


class InventoryMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryMovement
        fields = [
            "id",
            "product",
            "movement_type",
            "quantity_delta",
            "reference_type",
            "reference_id",
            "note",
            "created_by",
            "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at"]

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)
