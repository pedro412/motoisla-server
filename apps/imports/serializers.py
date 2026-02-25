from decimal import Decimal

from rest_framework import serializers

from apps.imports.models import InvoiceImportBatch, InvoiceImportLine


class InvoiceImportLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceImportLine
        fields = [
            "id",
            "line_no",
            "raw_line",
            "parsed_sku",
            "parsed_name",
            "parsed_qty",
            "parsed_unit_cost",
            "parsed_unit_price",
            "sku",
            "name",
            "qty",
            "unit_cost",
            "unit_price",
            "matched_product",
            "match_status",
            "is_selected",
            "notes",
        ]
        read_only_fields = [
            "id",
            "line_no",
            "raw_line",
            "parsed_sku",
            "parsed_name",
            "parsed_qty",
            "parsed_unit_cost",
            "parsed_unit_price",
            "match_status",
        ]


class InvoiceImportBatchSerializer(serializers.ModelSerializer):
    lines = InvoiceImportLineSerializer(many=True, read_only=True)

    class Meta:
        model = InvoiceImportBatch
        fields = [
            "id",
            "supplier",
            "parser",
            "raw_text",
            "status",
            "invoice_number",
            "invoice_date",
            "subtotal",
            "tax",
            "total",
            "created_by",
            "created_at",
            "confirmed_at",
            "lines",
        ]
        read_only_fields = ["id", "status", "created_by", "created_at", "confirmed_at", "lines"]

    def validate(self, attrs):
        supplier = attrs.get("supplier")
        parser = attrs.get("parser")
        if supplier and parser:
            if parser.supplier_id != supplier.id:
                raise serializers.ValidationError({"parser": "El parser no pertenece al proveedor seleccionado."})
            if not parser.is_active:
                raise serializers.ValidationError({"parser": "El parser seleccionado no esta activo."})

        for field in ("subtotal", "tax", "total"):
            value = attrs.get(field)
            if value is not None and value < Decimal("0"):
                raise serializers.ValidationError({field: f"{field} no puede ser negativo."})
        return attrs

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class InvoiceImportLineUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceImportLine
        fields = [
            "sku",
            "name",
            "qty",
            "unit_cost",
            "unit_price",
            "matched_product",
            "is_selected",
            "notes",
        ]

    def validate(self, attrs):
        qty = attrs.get("qty")
        if qty is not None and qty <= 0:
            raise serializers.ValidationError({"qty": "qty debe ser mayor a 0."})

        unit_cost = attrs.get("unit_cost")
        if unit_cost is not None and unit_cost < 0:
            raise serializers.ValidationError({"unit_cost": "unit_cost debe ser mayor o igual a 0."})

        unit_price = attrs.get("unit_price")
        if unit_price is not None and unit_price < 0:
            raise serializers.ValidationError({"unit_price": "unit_price debe ser mayor o igual a 0."})
        return attrs
