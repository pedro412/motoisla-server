from django.contrib import admin

from apps.catalog.models import Brand, Product, ProductImage, ProductType


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "brand", "product_type", "default_price", "is_active", "updated_at")
    list_filter = ("is_active", "brand", "product_type")
    search_fields = ("sku", "name", "brand_label", "product_type_label")
    inlines = [ProductImageInline]


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "is_primary", "created_at")
    list_filter = ("is_primary",)
    search_fields = ("product__sku", "product__name", "image_url")


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "normalized_name")


@admin.register(ProductType)
class ProductTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "normalized_name")
