import uuid

from django.db import models


def normalize_taxonomy_name(value: str) -> str:
    return (value or "").strip().upper()


class Brand(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80, unique=True)
    normalized_name = models.CharField(max_length=80, unique=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        self.name = (self.name or "").strip().upper()
        self.normalized_name = normalize_taxonomy_name(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80, unique=True)
    normalized_name = models.CharField(max_length=80, unique=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        self.name = (self.name or "").strip().upper()
        self.normalized_name = normalize_taxonomy_name(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sku = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    default_price = models.DecimalField(max_digits=12, decimal_places=2)
    brand = models.ForeignKey(Brand, null=True, blank=True, on_delete=models.SET_NULL)
    product_type = models.ForeignKey(ProductType, null=True, blank=True, on_delete=models.SET_NULL)
    brand_label = models.CharField(max_length=80, blank=True)
    product_type_label = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if self.brand_id:
            self.brand_label = self.brand.name
        if self.product_type_id:
            self.product_type_label = self.product_type.name
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sku} - {self.name}"


class ProductImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image_url = models.URLField(max_length=500)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_primary=True),
                name="unique_primary_image_per_product",
            )
        ]
