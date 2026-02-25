from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.services import record_audit
from apps.catalog.models import Product
from apps.common.permissions import RolePermission
from apps.imports.models import ImportStatus, InvoiceImportBatch, InvoiceImportLine, MatchStatus
from apps.imports.serializers import InvoiceImportBatchSerializer, InvoiceImportLineUpdateSerializer
from apps.imports.services import parse_invoice_text
from apps.inventory.models import InventoryMovement, MovementType
from apps.purchases.models import PurchaseReceipt, PurchaseReceiptLine, ReceiptStatus


class InvoiceImportBatchViewSet(viewsets.ModelViewSet):
    queryset = InvoiceImportBatch.objects.select_related("supplier", "parser", "created_by").prefetch_related("lines")
    serializer_class = InvoiceImportBatchSerializer
    permission_classes = [RolePermission]
    capability_map = {
        "list": ["imports.view"],
        "retrieve": ["imports.view"],
        "create": ["imports.manage"],
        "update": ["imports.manage"],
        "partial_update": ["imports.manage"],
        "destroy": ["imports.manage"],
        "parse": ["imports.manage"],
        "confirm": ["imports.manage"],
    }

    @action(detail=True, methods=["post"])
    def parse(self, request, pk=None):
        batch = self.get_object()
        if batch.status == ImportStatus.CONFIRMED:
            return Response({"code": "invalid_state", "detail": "Cannot parse a confirmed batch", "fields": {}}, status=400)

        parsed_rows = parse_invoice_text(batch.raw_text, batch.parser.parser_key)

        if not parsed_rows:
            return Response({"code": "invalid_raw_text", "detail": "No valid lines found to parse", "fields": {}}, status=400)

        with transaction.atomic():
            batch.lines.all().delete()
            for idx, (raw_line, parsed) in enumerate(parsed_rows, start=1):
                InvoiceImportLine.objects.create(
                    batch=batch,
                    line_no=idx,
                    raw_line=raw_line,
                    parsed_sku=parsed["sku"] or "",
                    parsed_name=parsed["name"] or "",
                    parsed_qty=parsed["qty"],
                    parsed_unit_cost=parsed["unit_cost"],
                    parsed_unit_price=parsed["unit_price"],
                    sku=parsed["sku"] or "",
                    name=parsed["name"] or "",
                    qty=parsed["qty"],
                    unit_cost=parsed["unit_cost"],
                    unit_price=parsed["unit_price"],
                    matched_product=parsed["matched_product"],
                    match_status=parsed["match_status"],
                )

            batch.status = ImportStatus.PARSED
            batch.save(update_fields=["status"])

            record_audit(
                actor=request.user,
                action="import.parse",
                entity_type="import_batch",
                entity_id=batch.id,
                payload={"lines": batch.lines.count()},
            )

        return Response(self.get_serializer(batch).data)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        batch = self.get_object()

        if batch.status == ImportStatus.CONFIRMED:
            receipt = PurchaseReceipt.objects.filter(source_import_batch=batch).first()
            payload = {"batch_id": str(batch.id)}
            if receipt:
                payload["purchase_receipt_id"] = str(receipt.id)
            return Response(payload, status=200)

        if batch.status != ImportStatus.PARSED:
            return Response(
                {"code": "invalid_state", "detail": "Batch must be parsed before confirm", "fields": {}},
                status=400,
            )

        selected = list(batch.lines.filter(is_selected=True).order_by("line_no"))
        if not selected:
            return Response({"code": "invalid_lines", "detail": "No selected lines to confirm", "fields": {}}, status=400)

        seen_skus = set()
        computed_subtotal = Decimal("0")
        for line in selected:
            normalized_sku = (line.sku or "").strip().upper()
            if not normalized_sku:
                return Response({"code": "invalid_lines", "detail": f"Line {line.line_no}: sku required", "fields": {}}, status=400)
            if normalized_sku in seen_skus:
                return Response(
                    {"code": "invalid_lines", "detail": f"Duplicate sku in selected lines: {normalized_sku}", "fields": {}},
                    status=400,
                )
            seen_skus.add(normalized_sku)

            if line.qty is None or line.qty <= 0:
                return Response(
                    {"code": "invalid_lines", "detail": f"Line {line.line_no}: qty must be > 0", "fields": {}},
                    status=400,
                )
            if line.unit_cost is None or line.unit_cost < 0:
                return Response(
                    {"code": "invalid_lines", "detail": f"Line {line.line_no}: unit_cost must be >= 0", "fields": {}},
                    status=400,
                )
            if line.unit_price is not None and line.unit_price < 0:
                return Response(
                    {"code": "invalid_lines", "detail": f"Line {line.line_no}: unit_price must be >= 0", "fields": {}},
                    status=400,
                )
            computed_subtotal += line.qty * line.unit_cost

        computed_subtotal = computed_subtotal.quantize(Decimal("0.01"))
        if batch.subtotal is not None and batch.subtotal.quantize(Decimal("0.01")) != computed_subtotal:
            return Response(
                {
                    "code": "subtotal_mismatch",
                    "detail": "Batch subtotal does not match selected lines subtotal",
                    "fields": {
                        "batch_subtotal": str(batch.subtotal),
                        "computed_subtotal": str(computed_subtotal),
                    },
                },
                status=400,
            )

        with transaction.atomic():
            receipt = PurchaseReceipt.objects.create(
                supplier=batch.supplier,
                invoice_number=batch.invoice_number,
                invoice_date=batch.invoice_date,
                status=ReceiptStatus.POSTED,
                subtotal=computed_subtotal,
                tax=batch.tax if batch.tax is not None else Decimal("0"),
                total=(computed_subtotal + (batch.tax if batch.tax is not None else Decimal("0"))).quantize(Decimal("0.01")),
                created_by=request.user,
                posted_at=timezone.now(),
                source_import_batch=batch,
            )

            for line in selected:
                normalized_sku = (line.sku or "").strip().upper()
                product = line.matched_product
                if product is None:
                    existing = Product.objects.filter(sku=normalized_sku).first()
                    if existing:
                        product = existing
                    else:
                        product = Product.objects.create(
                            sku=normalized_sku,
                            name=line.name or line.parsed_name or line.sku,
                            default_price=line.unit_price if line.unit_price is not None else line.unit_cost,
                        )

                PurchaseReceiptLine.objects.create(
                    receipt=receipt,
                    product=product,
                    qty=line.qty,
                    unit_cost=line.unit_cost,
                    unit_price=line.unit_price,
                )

                InventoryMovement.objects.create(
                    product=product,
                    movement_type=MovementType.INBOUND,
                    quantity_delta=line.qty,
                    reference_type="import_batch_confirm",
                    reference_id=str(batch.id),
                    note=f"Import batch line {line.line_no}",
                    created_by=request.user,
                )

                line.matched_product = product
                line.sku = normalized_sku
                line.match_status = MatchStatus.MATCHED_PRODUCT
                line.save(update_fields=["matched_product", "match_status", "sku"])

            batch.status = ImportStatus.CONFIRMED
            batch.confirmed_at = timezone.now()
            batch.save(update_fields=["status", "confirmed_at"])

            record_audit(
                actor=request.user,
                action="import.confirm",
                entity_type="import_batch",
                entity_id=batch.id,
                payload={"purchase_receipt_id": str(receipt.id)},
            )

        return Response({"batch_id": str(batch.id), "purchase_receipt_id": str(receipt.id)}, status=201)


class InvoiceImportLineViewSet(viewsets.GenericViewSet):
    queryset = InvoiceImportLine.objects.select_related("batch", "matched_product")
    serializer_class = InvoiceImportLineUpdateSerializer
    permission_classes = [RolePermission]
    capability_map = {
        "partial_update": ["imports.manage"],
    }

    def partial_update(self, request, pk=None):
        line = self.get_object()
        if line.batch.status == ImportStatus.CONFIRMED:
            return Response(
                {"code": "invalid_state", "detail": "Cannot edit lines from a confirmed batch", "fields": {}},
                status=400,
            )

        serializer = self.get_serializer(line, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record_audit(
            actor=request.user,
            action="import.line_update",
            entity_type="import_line",
            entity_id=line.id,
            payload={"batch_id": str(line.batch_id)},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
