from rest_framework import viewsets

from apps.common.permissions import RolePermission
from apps.suppliers.models import Supplier, SupplierInvoiceParser
from apps.suppliers.serializers import SupplierInvoiceParserSerializer, SupplierSerializer


class SupplierViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Supplier.objects.filter(is_active=True).order_by("name")
    serializer_class = SupplierSerializer
    permission_classes = [RolePermission]
    capability_map = {
        "list": ["imports.view"],
        "retrieve": ["imports.view"],
    }


class SupplierInvoiceParserViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SupplierInvoiceParserSerializer
    permission_classes = [RolePermission]
    capability_map = {
        "list": ["imports.view"],
        "retrieve": ["imports.view"],
    }

    def get_queryset(self):
        queryset = SupplierInvoiceParser.objects.filter(is_active=True).select_related("supplier").order_by("supplier__name", "parser_key")
        supplier_id = self.request.query_params.get("supplier")
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
        return queryset
