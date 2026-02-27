from rest_framework import serializers

from apps.suppliers.models import Supplier, SupplierInvoiceParser


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "code", "name", "is_active"]


class SupplierInvoiceParserSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierInvoiceParser
        fields = ["id", "supplier", "parser_key", "version", "description", "is_active"]
