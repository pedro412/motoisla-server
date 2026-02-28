from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.catalog.models import Brand, Product, ProductImage, ProductType
from apps.inventory.models import InventoryMovement, MovementType
from apps.inventory.models import InventoryMovement

User = get_user_model()


class CatalogAuditTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="admin123", role="ADMIN")

    def auth_as_admin(self):
        response = self.client.post(
            "/api/v1/auth/token/",
            {"username": "admin", "password": "admin123"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_product_create_update_delete_are_audited(self):
        self.auth_as_admin()
        created = self.client.post(
            "/api/v1/products/",
            {"sku": "CAT-001", "name": "Casco", "default_price": "100.00", "cost_price": "80.00", "is_active": True},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        product_id = created.data["id"]
        self.assertEqual(created.data["cost_price"], "80.00")

        updated = self.client.patch(
            f"/api/v1/products/{product_id}/",
            {"default_price": "120.00", "cost_price": "90.00"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["cost_price"], "90.00")

        deleted = self.client.delete(f"/api/v1/products/{product_id}/")
        self.assertEqual(deleted.status_code, 204)

        self.assertTrue(AuditLog.objects.filter(action="catalog.product.create", entity_id=product_id).exists())
        self.assertTrue(AuditLog.objects.filter(action="catalog.product.update", entity_id=product_id).exists())
        self.assertTrue(AuditLog.objects.filter(action="catalog.product.delete", entity_id=product_id).exists())

    def test_product_stock_adjustment_requires_reason_and_creates_inventory_movement(self):
        self.auth_as_admin()
        product = Product.objects.create(sku="CAT-003", name="Botas", default_price=Decimal("120.00"))

        missing_reason = self.client.patch(
            f"/api/v1/products/{product.id}/",
            {"stock": "5.00"},
            format="json",
        )
        self.assertEqual(missing_reason.status_code, 400)
        self.assertIn("stock_adjust_reason", missing_reason.data["fields"])
        self.assertEqual(InventoryMovement.objects.filter(product=product).count(), 0)

        adjusted = self.client.patch(
            f"/api/v1/products/{product.id}/",
            {"stock": "5.00", "stock_adjust_reason": "Conteo inicial"},
            format="json",
        )
        self.assertEqual(adjusted.status_code, 200)
        self.assertEqual(adjusted.data["stock"], "5.00")

        movement = InventoryMovement.objects.get(product=product)
        self.assertEqual(str(movement.quantity_delta), "5.00")
        self.assertEqual(movement.note, "Conteo inicial")

    def test_product_image_create_update_delete_are_audited(self):
        self.auth_as_admin()
        product = Product.objects.create(sku="CAT-002", name="Guantes", default_price=Decimal("50.00"))

        created = self.client.post(
            "/api/v1/product-images/",
            {"product": str(product.id), "image_url": "https://example.com/image-1.jpg", "is_primary": True},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        image_id = created.data["id"]

        updated = self.client.patch(
            f"/api/v1/product-images/{image_id}/",
            {"is_primary": False, "image_url": "https://example.com/image-2.jpg"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)

        deleted = self.client.delete(f"/api/v1/product-images/{image_id}/")
        self.assertEqual(deleted.status_code, 204)

        self.assertTrue(AuditLog.objects.filter(action="catalog.product_image.create", entity_id=image_id).exists())
        self.assertTrue(AuditLog.objects.filter(action="catalog.product_image.update", entity_id=image_id).exists())
        self.assertTrue(AuditLog.objects.filter(action="catalog.product_image.delete", entity_id=image_id).exists())


class PublicCatalogTests(APITestCase):
    def setUp(self):
        self.active = Product.objects.create(sku="PUB-001", name="Casco Publico", default_price=Decimal("150.00"), is_active=True)
        self.inactive = Product.objects.create(
            sku="PUB-002",
            name="Casco Inactivo",
            default_price=Decimal("180.00"),
            is_active=False,
        )
        ProductImage.objects.create(product=self.active, image_url="https://example.com/primary.jpg", is_primary=True)
        ProductImage.objects.create(product=self.active, image_url="https://example.com/secondary.jpg", is_primary=False)

    def test_public_catalog_list_is_readonly_and_does_not_require_auth(self):
        response = self.client.get("/api/v1/public/catalog/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["sku"], "PUB-001")
        self.assertEqual(response.data["results"][0]["primary_image_url"], "https://example.com/primary.jpg")

        post = self.client.post(
            "/api/v1/public/catalog/",
            {"sku": "X", "name": "X", "default_price": "1.00"},
            format="json",
        )
        self.assertEqual(post.status_code, 405)

    def test_public_catalog_search_filters_active_products(self):
        response = self.client.get("/api/v1/public/catalog/?q=casco")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["sku"], "PUB-001")

        response_inactive = self.client.get("/api/v1/public/catalog/?q=inactivo")
        self.assertEqual(response_inactive.status_code, 200)
        self.assertEqual(response_inactive.data["count"], 0)

    def test_public_catalog_detail_by_sku(self):
        response = self.client.get("/api/v1/public/catalog/PUB-001/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["sku"], "PUB-001")
        self.assertEqual(response.data["primary_image_url"], "https://example.com/primary.jpg")

        not_found = self.client.get("/api/v1/public/catalog/PUB-002/")
        self.assertEqual(not_found.status_code, 404)


class ProductListFiltersTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin_filters", password="admin123", role="ADMIN")
        token = self.client.post(
            "/api/v1/auth/token/",
            {"username": "admin_filters", "password": "admin123"},
            format="json",
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        self.brand_ls2 = Brand.objects.create(name="LS2")
        self.brand_agv = Brand.objects.create(name="AGV")
        self.type_helmets = ProductType.objects.create(name="CASCOS")
        self.type_gloves = ProductType.objects.create(name="GUANTES")

        self.product_with_stock = Product.objects.create(
            sku="FLT-001",
            name="Casco LS2",
            default_price=Decimal("100.00"),
            brand=self.brand_ls2,
            product_type=self.type_helmets,
        )
        self.product_without_stock = Product.objects.create(
            sku="FLT-002",
            name="Guantes AGV",
            default_price=Decimal("80.00"),
            brand=self.brand_agv,
            product_type=self.type_gloves,
        )

        InventoryMovement.objects.create(
            product=self.product_with_stock,
            movement_type=MovementType.INBOUND,
            quantity_delta=Decimal("3.00"),
            reference_type="seed",
            reference_id="seed-1",
            note="seed",
            created_by=self.admin,
        )

    def test_products_list_filters_by_brand_product_type_and_stock(self):
        by_brand = self.client.get(f"/api/v1/products/?brand={self.brand_ls2.id}")
        self.assertEqual(by_brand.status_code, 200)
        self.assertEqual(by_brand.data["count"], 1)
        self.assertEqual(by_brand.data["results"][0]["sku"], "FLT-001")

        by_product_type = self.client.get(f"/api/v1/products/?product_type={self.type_gloves.id}")
        self.assertEqual(by_product_type.status_code, 200)
        self.assertEqual(by_product_type.data["count"], 1)
        self.assertEqual(by_product_type.data["results"][0]["sku"], "FLT-002")

        with_stock = self.client.get("/api/v1/products/?has_stock=true")
        self.assertEqual(with_stock.status_code, 200)
        self.assertEqual(with_stock.data["count"], 1)
        self.assertEqual(with_stock.data["results"][0]["sku"], "FLT-001")
