from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.services import record_audit
from apps.catalog.models import Brand, Product, ProductType, normalize_taxonomy_name
from apps.common.permissions import RolePermission
from apps.imports.models import ImportStatus, InvoiceImportBatch, InvoiceImportLine, MatchStatus
from apps.imports.serializers import (
    InvoiceImportBatchSerializer,
    InvoiceImportLineUpdateSerializer,
    PreviewConfirmBatchSerializer,
)
from apps.imports.services import parse_invoice_text
from apps.inventory.models import InventoryMovement, MovementType
from apps.purchases.models import PurchaseReceipt, PurchaseReceiptLine, ReceiptStatus


class ImportValidationError(Exception):
    def __init__(self, code: str, detail: str, fields: dict | None = None, status_code: int = 400):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.fields = fields or {}
        self.status_code = status_code


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
        "preview_confirm": ["imports.manage"],
    }

    def _resolve_taxonomy(self, selected: list[InvoiceImportLine]):
        resolved = {}
        missing_lines = []
        brand_cache: dict[str, Brand | None] = {}
        type_cache: dict[str, ProductType | None] = {}

        for line in selected:
            brand = line.brand
            product_type = line.product_type

            brand_label = (line.brand_name or "").strip()
            product_type_label = (line.product_type_name or "").strip()

            missing = []

            if brand is None and brand_label:
                key = normalize_taxonomy_name(brand_label)
                if key not in brand_cache:
                    brand_cache[key] = Brand.objects.filter(normalized_name=key).first()
                brand = brand_cache[key]
            if product_type is None and product_type_label:
                key = normalize_taxonomy_name(product_type_label)
                if key not in type_cache:
                    type_cache[key] = ProductType.objects.filter(normalized_name=key).first()
                product_type = type_cache[key]

            if brand is not None and not brand_label:
                brand_label = brand.name
            if product_type is not None and not product_type_label:
                product_type_label = product_type.name

            if not brand_label:
                missing.append("brand")
            elif brand is None:
                missing.append("brand")

            if not product_type_label:
                missing.append("product_type")
            elif product_type is None:
                missing.append("product_type")

            if missing:
                missing_lines.append(
                    {
                        "line_no": line.line_no,
                        "brand_name": brand_label,
                        "product_type_name": product_type_label,
                        "missing": missing,
                    }
                )
                continue

            resolved[line.id] = (brand, product_type, brand_label, product_type_label)

        if missing_lines:
            raise ImportValidationError(
                "taxonomy_not_found",
                "Brand/Product type must exist before confirm",
                fields={"lines": missing_lines},
            )

        return resolved

    def _validate_selected_lines(self, selected: list[InvoiceImportLine], batch_subtotal: Decimal | None) -> Decimal:
        if not selected:
            raise ImportValidationError("invalid_lines", "No selected lines to confirm")

        seen_skus = set()
        computed_subtotal = Decimal("0")

        for line in selected:
            normalized_sku = (line.sku or "").strip().upper()
            if not normalized_sku:
                raise ImportValidationError("invalid_lines", f"Line {line.line_no}: sku required")
            if normalized_sku in seen_skus:
                raise ImportValidationError("invalid_lines", f"Duplicate sku in selected lines: {normalized_sku}")
            seen_skus.add(normalized_sku)

            if line.qty is None or line.qty <= 0:
                raise ImportValidationError("invalid_lines", f"Line {line.line_no}: qty must be > 0")
            if line.unit_cost is None or line.unit_cost < 0:
                raise ImportValidationError("invalid_lines", f"Line {line.line_no}: unit_cost must be >= 0")
            if line.unit_price is not None and line.unit_price < 0:
                raise ImportValidationError("invalid_lines", f"Line {line.line_no}: unit_price must be >= 0")
            if line.public_price is not None and line.public_price < 0:
                raise ImportValidationError("invalid_lines", f"Line {line.line_no}: public_price must be >= 0")
            if not (line.brand_name or "").strip() and not line.brand_id:
                raise ImportValidationError("invalid_lines", f"Line {line.line_no}: brand_name is required")
            if not (line.product_type_name or "").strip() and not line.product_type_id:
                raise ImportValidationError("invalid_lines", f"Line {line.line_no}: product_type_name is required")

            computed_subtotal += line.qty * line.unit_cost

        computed_subtotal = computed_subtotal.quantize(Decimal("0.01"))
        if batch_subtotal is not None and batch_subtotal.quantize(Decimal("0.01")) != computed_subtotal:
            raise ImportValidationError(
                "subtotal_mismatch",
                "Batch subtotal does not match selected lines subtotal",
                fields={
                    "batch_subtotal": str(batch_subtotal),
                    "computed_subtotal": str(computed_subtotal),
                },
            )

        return computed_subtotal

    def _confirm_batch(self, batch: InvoiceImportBatch, actor) -> PurchaseReceipt:
        selected = list(batch.lines.filter(is_selected=True).order_by("line_no"))
        computed_subtotal = self._validate_selected_lines(selected, batch.subtotal)
        taxonomy_by_line = self._resolve_taxonomy(selected)

        receipt = PurchaseReceipt.objects.create(
            supplier=batch.supplier,
            invoice_number=batch.invoice_number,
            invoice_date=batch.invoice_date,
            status=ReceiptStatus.POSTED,
            subtotal=computed_subtotal,
            tax=batch.tax if batch.tax is not None else Decimal("0"),
            total=(computed_subtotal + (batch.tax if batch.tax is not None else Decimal("0"))).quantize(Decimal("0.01")),
            created_by=actor,
            posted_at=timezone.now(),
            source_import_batch=batch,
        )

        for line in selected:
            normalized_sku = (line.sku or "").strip().upper()
            brand, product_type, brand_label, product_type_label = taxonomy_by_line[line.id]
            product = line.matched_product
            if product is None:
                existing = Product.objects.filter(sku=normalized_sku).first()
                if existing:
                    product = existing
                else:
                    product = Product.objects.create(
                        sku=normalized_sku,
                        name=line.name or line.parsed_name or line.sku,
                        brand=brand,
                        product_type=product_type,
                        brand_label=brand_label,
                        product_type_label=product_type_label,
                        default_price=(
                            line.public_price
                            if line.public_price is not None
                            else line.unit_price
                            if line.unit_price is not None
                            else line.unit_cost
                        ),
                    )
            product_fields = []
            if product.brand_id is None and brand is not None:
                product.brand = brand
                product_fields.append("brand")
            if product.product_type_id is None and product_type is not None:
                product.product_type = product_type
                product_fields.append("product_type")
            if not product.brand_label and brand_label:
                product.brand_label = brand_label
                product_fields.append("brand_label")
            if not product.product_type_label and product_type_label:
                product.product_type_label = product_type_label
                product_fields.append("product_type_label")
            if product_fields:
                product.save(update_fields=product_fields)

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
                created_by=actor,
            )

            line.matched_product = product
            line.sku = normalized_sku
            line.brand = brand
            line.product_type = product_type
            line.brand_name = brand_label
            line.product_type_name = product_type_label
            line.match_status = MatchStatus.MATCHED_PRODUCT
            line.save(
                update_fields=[
                    "matched_product",
                    "match_status",
                    "sku",
                    "brand",
                    "product_type",
                    "brand_name",
                    "product_type_name",
                ]
            )

        batch.status = ImportStatus.CONFIRMED
        batch.confirmed_at = timezone.now()
        batch.save(update_fields=["status", "confirmed_at"])

        record_audit(
            actor=actor,
            action="import.confirm",
            entity_type="import_batch",
            entity_id=batch.id,
            payload={"purchase_receipt_id": str(receipt.id)},
        )
        return receipt

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
                    public_price=parsed["public_price"],
                    brand=parsed["matched_product"].brand if parsed["matched_product"] else None,
                    product_type=parsed["matched_product"].product_type if parsed["matched_product"] else None,
                    brand_name=(
                        parsed["matched_product"].brand.name
                        if parsed["matched_product"] and parsed["matched_product"].brand_id
                        else ""
                    ),
                    product_type_name=(
                        parsed["matched_product"].product_type.name
                        if parsed["matched_product"] and parsed["matched_product"].product_type_id
                        else ""
                    ),
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

        with transaction.atomic():
            try:
                receipt = self._confirm_batch(batch, request.user)
            except ImportValidationError as exc:
                return Response({"code": exc.code, "detail": exc.detail, "fields": exc.fields}, status=exc.status_code)

        return Response({"batch_id": str(batch.id), "purchase_receipt_id": str(receipt.id)}, status=201)

    @action(detail=False, methods=["post"], url_path="preview-confirm")
    def preview_confirm(self, request):
        serializer = PreviewConfirmBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        with transaction.atomic():
            batch = InvoiceImportBatch.objects.create(
                supplier=payload["supplier"],
                parser=payload["parser"],
                raw_text=payload["raw_text"],
                status=ImportStatus.PARSED,
                invoice_number=payload.get("invoice_number"),
                invoice_date=payload.get("invoice_date"),
                subtotal=payload.get("subtotal"),
                tax=payload.get("tax"),
                total=payload.get("total"),
                created_by=request.user,
            )

            for idx, line_data in enumerate(payload["lines"], start=1):
                normalized_sku = (line_data.get("sku") or "").strip().upper()
                matched_product = Product.objects.filter(sku=normalized_sku).first() if normalized_sku else None
                if not normalized_sku:
                    match_status = MatchStatus.INVALID
                elif matched_product:
                    match_status = MatchStatus.MATCHED_PRODUCT
                else:
                    match_status = MatchStatus.NEW_PRODUCT

                InvoiceImportLine.objects.create(
                    batch=batch,
                    line_no=idx,
                    raw_line=f"{normalized_sku} {line_data.get('name', '')}".strip(),
                    parsed_sku=normalized_sku,
                    parsed_name=line_data.get("name", "") or "",
                    parsed_qty=line_data.get("qty"),
                    parsed_unit_cost=line_data.get("unit_cost"),
                    parsed_unit_price=line_data.get("unit_price"),
                    sku=normalized_sku,
                    name=line_data.get("name", "") or "",
                    qty=line_data.get("qty"),
                    unit_cost=line_data.get("unit_cost"),
                    unit_price=line_data.get("unit_price"),
                    public_price=line_data.get("public_price"),
                    brand_name=(line_data.get("brand_name") or "").strip(),
                    product_type_name=(line_data.get("product_type_name") or "").strip(),
                    brand=line_data.get("brand"),
                    product_type=line_data.get("product_type"),
                    matched_product=matched_product,
                    match_status=match_status,
                    is_selected=line_data.get("is_selected", True),
                    notes=line_data.get("notes", "") or "",
                )

            try:
                receipt = self._confirm_batch(batch, request.user)
            except ImportValidationError as exc:
                return Response({"code": exc.code, "detail": exc.detail, "fields": exc.fields}, status=exc.status_code)

        return Response({"batch_id": str(batch.id), "purchase_receipt_id": str(receipt.id)}, status=201)


class InvoiceImportLineViewSet(viewsets.GenericViewSet):
    queryset = InvoiceImportLine.objects.select_related("batch", "matched_product", "brand", "product_type")
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
