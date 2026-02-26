from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.expenses.models import Expense

User = get_user_model()


class ExpensesApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin_exp", password="admin123", role="ADMIN")
        self.cashier = User.objects.create_user(username="cashier_exp", password="cashier123", role="CASHIER")

    def auth_as(self, username, password):
        token = self.client.post(
            "/api/v1/auth/token/",
            {"username": username, "password": password},
            format="json",
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_admin_can_crud_expenses_with_filters(self):
        self.auth_as("admin_exp", "admin123")
        today = timezone.now().date()
        create_response = self.client.post(
            "/api/v1/expenses/",
            {
                "category": "Rent",
                "description": "Local rent",
                "amount": "3500.00",
                "expense_date": str(today),
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        expense_id = create_response.data["id"]

        update_response = self.client.patch(
            f"/api/v1/expenses/{expense_id}/",
            {"amount": "3600.00"},
            format="json",
        )
        self.assertEqual(update_response.status_code, 200)

        list_response = self.client.get(
            "/api/v1/expenses/",
            {
                "date_from": str(today - timedelta(days=1)),
                "date_to": str(today + timedelta(days=1)),
                "category": "rent",
            },
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data["count"], 1)
        self.assertEqual(Decimal(str(list_response.data["results"][0]["amount"])), Decimal("3600.00"))

        delete_response = self.client.delete(f"/api/v1/expenses/{expense_id}/")
        self.assertEqual(delete_response.status_code, 204)

        self.assertTrue(AuditLog.objects.filter(action="expenses.create", entity_id=expense_id).exists())
        self.assertTrue(AuditLog.objects.filter(action="expenses.update", entity_id=expense_id).exists())
        self.assertTrue(AuditLog.objects.filter(action="expenses.delete", entity_id=expense_id).exists())

    def test_non_admin_cannot_access_expenses(self):
        self.auth_as("cashier_exp", "cashier123")
        response = self.client.get("/api/v1/expenses/")
        self.assertEqual(response.status_code, 403)

    def test_amount_must_be_positive(self):
        self.auth_as("admin_exp", "admin123")
        response = self.client.post(
            "/api/v1/expenses/",
            {
                "category": "Utilities",
                "description": "Power bill",
                "amount": "0.00",
                "expense_date": str(timezone.now().date()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("amount", response.data["fields"])
        self.assertEqual(Expense.objects.count(), 0)
