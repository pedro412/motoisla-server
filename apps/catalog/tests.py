from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.catalog.models import Product, ProductImage

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
            {"sku": "CAT-001", "name": "Casco", "default_price": "100.00", "is_active": True},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        product_id = created.data["id"]

        updated = self.client.patch(
            f"/api/v1/products/{product_id}/",
            {"default_price": "120.00"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)

        deleted = self.client.delete(f"/api/v1/products/{product_id}/")
        self.assertEqual(deleted.status_code, 204)

        self.assertTrue(AuditLog.objects.filter(action="catalog.product.create", entity_id=product_id).exists())
        self.assertTrue(AuditLog.objects.filter(action="catalog.product.update", entity_id=product_id).exists())
        self.assertTrue(AuditLog.objects.filter(action="catalog.product.delete", entity_id=product_id).exists())

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
