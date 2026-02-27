from rest_framework import serializers

from apps.inventory.models import InventoryMovement
from apps.purchases.models import PurchaseReceipt, PurchaseReceiptLine


def receipt_can_delete(receipt: PurchaseReceipt) -> bool:
    if receipt.status != "POSTED":
        return True

    for line in receipt.lines.all():
        current_stock = InventoryMovement.current_stock(line.product_id)
        if current_stock < line.qty:
            return False
    return True


class PurchaseReceiptLineSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = PurchaseReceiptLine
        fields = ["id", "product", "product_sku", "product_name", "qty", "unit_cost", "unit_price"]
        read_only_fields = ["id"]


class PurchaseReceiptSerializer(serializers.ModelSerializer):
    lines = PurchaseReceiptLineSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    supplier_code = serializers.CharField(source="supplier.code", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    can_delete = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseReceipt
        fields = [
            "id",
            "supplier",
            "supplier_name",
            "supplier_code",
            "invoice_number",
            "invoice_date",
            "status",
            "subtotal",
            "tax",
            "total",
            "source_import_batch",
            "created_by",
            "created_by_username",
            "can_delete",
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

    def get_can_delete(self, obj):
        return receipt_can_delete(obj)
