import uuid

from django.db import models


class ImportStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PARSED = "PARSED", "Parsed"
    CONFIRMED = "CONFIRMED", "Confirmed"
    CANCELLED = "CANCELLED", "Cancelled"
    ERROR = "ERROR", "Error"


class MatchStatus(models.TextChoices):
    NEW_PRODUCT = "NEW_PRODUCT", "New Product"
    MATCHED_PRODUCT = "MATCHED_PRODUCT", "Matched Product"
    AMBIGUOUS = "AMBIGUOUS", "Ambiguous"
    INVALID = "INVALID", "Invalid"


class InvoiceImportBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.PROTECT)
    parser = models.ForeignKey("suppliers.SupplierInvoiceParser", on_delete=models.PROTECT)
    raw_text = models.TextField()
    status = models.CharField(max_length=16, choices=ImportStatus.choices, default=ImportStatus.DRAFT)
    invoice_number = models.CharField(max_length=64, null=True, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    tax = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)


class InvoiceImportLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(InvoiceImportBatch, on_delete=models.CASCADE, related_name="lines")
    line_no = models.PositiveIntegerField()
    raw_line = models.TextField()
    parsed_sku = models.CharField(max_length=64, blank=True)
    parsed_name = models.CharField(max_length=255, blank=True)
    parsed_qty = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    parsed_unit_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    parsed_unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sku = models.CharField(max_length=64, blank=True)
    name = models.CharField(max_length=255, blank=True)
    qty = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    public_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    brand_name = models.CharField(max_length=80, blank=True)
    product_type_name = models.CharField(max_length=80, blank=True)
    brand = models.ForeignKey("catalog.Brand", null=True, blank=True, on_delete=models.SET_NULL)
    product_type = models.ForeignKey("catalog.ProductType", null=True, blank=True, on_delete=models.SET_NULL)
    matched_product = models.ForeignKey("catalog.Product", null=True, blank=True, on_delete=models.SET_NULL)
    match_status = models.CharField(max_length=20, choices=MatchStatus.choices, default=MatchStatus.INVALID)
    is_selected = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["batch", "line_no"], name="unique_batch_line_no")]
