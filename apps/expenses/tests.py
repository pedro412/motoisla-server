from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.expenses.models import Expense, ExpenseStatus, ExpenseType, FixedExpenseTemplate

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

    def test_admin_can_manage_fixed_templates_generate_and_summarize_expenses(self):
        self.auth_as("admin_exp", "admin123")
        template_response = self.client.post(
            "/api/v1/fixed-expense-templates/",
            {
                "name": "Renta local",
                "category": "Rent",
                "default_amount": "3500.00",
                "description": "Pago mensual de renta",
                "charge_day": 5,
                "is_active": True,
                "notes": "Contrato principal",
            },
            format="json",
        )
        self.assertEqual(template_response.status_code, 201)
        template_id = template_response.data["id"]

        second_template = FixedExpenseTemplate.objects.create(
            name="Internet",
            category="Utilities",
            default_amount=Decimal("999.00"),
            description="Fibra",
            charge_day=12,
            is_active=False,
            created_by=self.admin,
        )

        list_templates = self.client.get("/api/v1/fixed-expense-templates/?is_active=true")
        self.assertEqual(list_templates.status_code, 200)
        self.assertEqual(list_templates.data["count"], 1)

        patch_template = self.client.patch(
            f"/api/v1/fixed-expense-templates/{template_id}/",
            {"default_amount": "3600.00"},
            format="json",
        )
        self.assertEqual(patch_template.status_code, 200)

        generated = self.client.post(
            "/api/v1/expenses/generate-fixed/",
            {"month": "2026-03"},
            format="json",
        )
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(generated.data["created_count"], 1)
        self.assertEqual(generated.data["existing_count"], 0)

        generated_again = self.client.post(
            "/api/v1/expenses/generate-fixed/",
            {"month": "2026-03"},
            format="json",
        )
        self.assertEqual(generated_again.status_code, 200)
        self.assertEqual(generated_again.data["created_count"], 0)
        self.assertEqual(generated_again.data["existing_count"], 1)

        expense = Expense.objects.get(template_id=template_id, month_bucket="2026-03-01")
        self.assertEqual(expense.expense_type, ExpenseType.FIXED)
        self.assertEqual(expense.status, ExpenseStatus.PENDING)
        self.assertEqual(expense.amount, Decimal("3600.00"))
        self.assertEqual(expense.due_date.isoformat(), "2026-03-05")
        self.assertFalse(Expense.objects.filter(template=second_template, month_bucket="2026-03-01").exists())

        mark_paid = self.client.patch(
            f"/api/v1/expenses/{expense.id}/",
            {
                "status": ExpenseStatus.PAID,
                "amount": "3650.00",
                "expense_date": "2026-03-06",
            },
            format="json",
        )
        self.assertEqual(mark_paid.status_code, 200)
        expense.refresh_from_db()
        self.assertEqual(expense.status, ExpenseStatus.PAID)
        self.assertEqual(expense.paid_by, self.admin)
        self.assertIsNotNone(expense.paid_at)
        self.assertEqual(expense.amount, Decimal("3650.00"))
        self.assertEqual(expense.month_bucket.isoformat(), "2026-03-01")

        summary = self.client.get("/api/v1/expenses/summary/?month=2026-03")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(Decimal(str(summary.data["fixed_paid_total"])), Decimal("3650.00"))
        self.assertEqual(summary.data["fixed_paid_count"], 1)
        self.assertEqual(Decimal(str(summary.data["fixed_pending_total"])), Decimal("0.00"))
        self.assertEqual(summary.data["fixed_pending_count"], 0)

        self.assertTrue(AuditLog.objects.filter(action="expenses.template.create", entity_id=template_id).exists())
        self.assertTrue(AuditLog.objects.filter(action="expenses.template.update", entity_id=template_id).exists())
        self.assertTrue(AuditLog.objects.filter(action="expenses.generate_fixed", entity_id="2026-03").exists())

    def test_admin_can_manage_variable_expenses_with_filters_and_cancel(self):
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
            {"amount": "3600.00", "description": "Main local rent"},
            format="json",
        )
        self.assertEqual(update_response.status_code, 200)

        pending = Expense.objects.create(
            category="Utilities",
            description="Power bill",
            amount=Decimal("500.00"),
            expense_date=today,
            expense_type=ExpenseType.VARIABLE,
            status=ExpenseStatus.PENDING,
            month_bucket=today.replace(day=1),
            due_date=today,
            created_by=self.admin,
        )

        list_response = self.client.get(
            "/api/v1/expenses/",
            {
                "month": today.strftime("%Y-%m"),
                "status": ExpenseStatus.PAID,
                "expense_type": ExpenseType.VARIABLE,
                "category": "rent",
            },
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data["count"], 1)
        self.assertEqual(Decimal(str(list_response.data["results"][0]["amount"])), Decimal("3600.00"))

        cancel_response = self.client.patch(
            f"/api/v1/expenses/{pending.id}/",
            {"status": ExpenseStatus.CANCELLED},
            format="json",
        )
        self.assertEqual(cancel_response.status_code, 200)
        pending.refresh_from_db()
        self.assertEqual(pending.status, ExpenseStatus.CANCELLED)
        self.assertIsNone(pending.paid_at)

        invalid_back_to_pending = self.client.patch(
            f"/api/v1/expenses/{pending.id}/",
            {"status": ExpenseStatus.PENDING},
            format="json",
        )
        self.assertEqual(invalid_back_to_pending.status_code, 400)
        self.assertIn("status", invalid_back_to_pending.data["fields"])

        summary = self.client.get(f"/api/v1/expenses/summary/?month={today:%Y-%m}")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(Decimal(str(summary.data["actual_paid_total"])), Decimal("3600.00"))
        self.assertEqual(Decimal(str(summary.data["pending_commitments_total"])), Decimal("0.00"))
        self.assertEqual(summary.data["variable_paid_count"], 1)

        self.assertTrue(AuditLog.objects.filter(action="expenses.create", entity_id=expense_id).exists())
        self.assertTrue(AuditLog.objects.filter(action="expenses.update", entity_id=expense_id).exists())

    def test_non_admin_cannot_access_expenses(self):
        self.auth_as("cashier_exp", "cashier123")
        response = self.client.get("/api/v1/expenses/")
        self.assertEqual(response.status_code, 403)

    def test_amount_and_template_rules_are_enforced(self):
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

        template = FixedExpenseTemplate.objects.create(
            name="Internet",
            category="Utilities",
            default_amount=Decimal("500.00"),
            charge_day=10,
            created_by=self.admin,
        )
        invalid_variable = self.client.post(
            "/api/v1/expenses/",
            {
                "category": "Utilities",
                "description": "Bad variable",
                "amount": "120.00",
                "expense_date": str(timezone.now().date()),
                "expense_type": ExpenseType.VARIABLE,
                "template": str(template.id),
            },
            format="json",
        )
        self.assertEqual(invalid_variable.status_code, 400)
        self.assertIn("template", invalid_variable.data["fields"])
        self.assertEqual(Expense.objects.count(), 0)

    def test_paid_only_expenses_count_in_sales_report(self):
        self.auth_as("admin_exp", "admin123")
        today = timezone.now().date()
        Expense.objects.create(
            category="Rent",
            description="Paid rent",
            amount=Decimal("1000.00"),
            expense_date=today,
            status=ExpenseStatus.PAID,
            month_bucket=today.replace(day=1),
            paid_by=self.admin,
            created_by=self.admin,
        )
        Expense.objects.create(
            category="Utilities",
            description="Pending utility",
            amount=Decimal("200.00"),
            expense_date=today,
            status=ExpenseStatus.PENDING,
            month_bucket=today.replace(day=1),
            due_date=today,
            created_by=self.admin,
        )

        from apps.sales.views_metrics import SalesReportView

        expenses = SalesReportView._expenses_queryset(today - timedelta(days=1), today + timedelta(days=1))
        self.assertEqual(expenses.count(), 1)
        self.assertEqual(expenses.first().description, "Paid rent")
