from rest_framework import serializers

from apps.catalog.models import Brand, Product, ProductImage, ProductType


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "product", "image_url", "is_primary", "created_at"]
        read_only_fields = ["id", "created_at"]


class ProductSerializer(serializers.ModelSerializer):
    stock = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    product_type_name = serializers.CharField(source="product_type.name", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "sku",
            "name",
            "default_price",
            "brand",
            "brand_name",
            "product_type",
            "product_type_name",
            "brand_label",
            "product_type_label",
            "is_active",
            "stock",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "stock"]


class PublicCatalogProductSerializer(serializers.ModelSerializer):
    primary_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "sku",
            "name",
            "default_price",
            "primary_image_url",
            "updated_at",
        ]
        read_only_fields = fields

    def get_primary_image_url(self, obj):
        primary = next((image for image in obj.images.all() if image.is_primary), None)
        if primary:
            return primary.image_url
        first_image = next(iter(obj.images.all()), None)
        return first_image.image_url if first_image else None


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "name", "normalized_name", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "normalized_name", "created_at", "updated_at"]


class ProductTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductType
        fields = ["id", "name", "normalized_name", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "normalized_name", "created_at", "updated_at"]
