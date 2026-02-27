from decimal import Decimal

from rest_framework import serializers

from apps.imports.models import InvoiceImportBatch, InvoiceImportLine
from apps.catalog.models import Brand, ProductType
from apps.suppliers.models import Supplier, SupplierInvoiceParser


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
            "public_price",
            "brand_name",
            "product_type_name",
            "brand",
            "product_type",
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
            "public_price",
            "brand_name",
            "product_type_name",
            "brand",
            "product_type",
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

        public_price = attrs.get("public_price")
        if public_price is not None and public_price < 0:
            raise serializers.ValidationError({"public_price": "public_price debe ser mayor o igual a 0."})
        return attrs


class PreviewConfirmLineSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=64, allow_blank=True)
    name = serializers.CharField(max_length=255, allow_blank=True, required=False, default="")
    qty = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    public_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    brand_name = serializers.CharField(max_length=80, required=False, allow_blank=True, allow_null=True)
    product_type_name = serializers.CharField(max_length=80, required=False, allow_blank=True, allow_null=True)
    brand_id = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(), required=False, allow_null=True, source="brand"
    )
    product_type_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductType.objects.all(), required=False, allow_null=True, source="product_type"
    )
    is_selected = serializers.BooleanField(required=False, default=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class PreviewConfirmBatchSerializer(serializers.Serializer):
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    parser = serializers.PrimaryKeyRelatedField(queryset=SupplierInvoiceParser.objects.all())
    invoice_number = serializers.CharField(max_length=64, required=False, allow_blank=True, allow_null=True)
    invoice_date = serializers.DateField(required=False, allow_null=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    tax = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    raw_text = serializers.CharField()
    lines = PreviewConfirmLineSerializer(many=True)

    def validate(self, attrs):
        supplier = attrs["supplier"]
        parser = attrs["parser"]
        if parser.supplier_id != supplier.id:
            raise serializers.ValidationError({"parser": "El parser no pertenece al proveedor seleccionado."})
        if not parser.is_active:
            raise serializers.ValidationError({"parser": "El parser seleccionado no esta activo."})

        for field in ("subtotal", "tax", "total"):
            value = attrs.get(field)
            if value is not None and value < Decimal("0"):
                raise serializers.ValidationError({field: f"{field} no puede ser negativo."})

        lines = attrs.get("lines", [])
        if not lines:
            raise serializers.ValidationError({"lines": "Debes enviar al menos una linea en preview."})
        return attrs
