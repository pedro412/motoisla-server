from rest_framework import serializers

from apps.purchases.models import PurchaseReceipt, PurchaseReceiptLine


class PurchaseReceiptLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseReceiptLine
        fields = ["id", "product", "qty", "unit_cost", "unit_price"]
        read_only_fields = ["id"]


class PurchaseReceiptSerializer(serializers.ModelSerializer):
    lines = PurchaseReceiptLineSerializer(many=True)

    class Meta:
        model = PurchaseReceipt
        fields = [
            "id",
            "supplier",
            "invoice_number",
            "invoice_date",
            "status",
            "subtotal",
            "tax",
            "total",
            "source_import_batch",
            "created_by",
            "posted_at",
            "created_at",
            "lines",
        ]
        read_only_fields = ["id", "status", "created_by", "posted_at", "created_at"]

    def validate(self, attrs):
        lines = attrs.get("lines", [])
        if not lines:
            raise serializers.ValidationError({"lines": "At least one line is required"})

        seen_products = set()
        for line in lines:
            product_id = str(line["product"].id)
            if product_id in seen_products:
                raise serializers.ValidationError({"lines": f"Duplicate product in receipt: {line['product'].sku}"})
            seen_products.add(product_id)

            if line["qty"] <= 0:
                raise serializers.ValidationError({"qty": "qty must be > 0"})
            if line["unit_cost"] < 0:
                raise serializers.ValidationError({"unit_cost": "unit_cost must be >= 0"})
            if line.get("unit_price") is not None and line["unit_price"] < 0:
                raise serializers.ValidationError({"unit_price": "unit_price must be >= 0"})
        return attrs

    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        validated_data["created_by"] = self.context["request"].user
        receipt = super().create(validated_data)
        for line in lines:
            PurchaseReceiptLine.objects.create(receipt=receipt, **line)
        return receipt
