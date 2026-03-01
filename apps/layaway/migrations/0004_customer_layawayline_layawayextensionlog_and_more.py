# Generated manually for customer-backed layaway flows.

import django.db.models.deletion
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
        ("layaway", "0003_customercredit_customercredit_phone_idx_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Customer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("phone", models.CharField(max_length=50)),
                ("phone_normalized", models.CharField(max_length=50, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("notes", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["phone_normalized"], name="customer_phone_norm_idx"),
                    models.Index(fields=["name"], name="customer_name_idx"),
                ]
            },
        ),
        migrations.AddField(
            model_name="customercredit",
            name="customer",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="credit",
                to="layaway.customer",
            ),
        ),
        migrations.AddField(
            model_name="layaway",
            name="amount_paid",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="layaway",
            name="customer",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="layaways",
                to="layaway.customer",
            ),
        ),
        migrations.AddField(
            model_name="layaway",
            name="notes",
            field=models.CharField(blank=True, default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="layaway",
            name="settled_sale_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="layaway",
            name="subtotal",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="layaway",
            name="total",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="layaway",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
            preserve_default=False,
        ),
        migrations.AddIndex(
            model_name="layaway",
            index=models.Index(fields=["customer", "status"], name="layaway_customer_status_idx"),
        ),
        migrations.AddConstraint(
            model_name="layaway",
            constraint=models.CheckConstraint(check=models.Q(("amount_paid__gte", 0)), name="layaway_amount_paid_gte_zero"),
        ),
        migrations.AddField(
            model_name="layawaypayment",
            name="card_plan_code",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="layawaypayment",
            name="card_plan_label",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="layawaypayment",
            name="card_type",
            field=models.CharField(blank=True, default="", max_length=12),
        ),
        migrations.AddField(
            model_name="layawaypayment",
            name="commission_rate",
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=6, null=True),
        ),
        migrations.AddField(
            model_name="layawaypayment",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="layaway_payments",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="layawaypayment",
            name="installments_months",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="layawaypayment",
            name="method",
            field=models.CharField(default="CASH", max_length=20),
        ),
        migrations.AddField(
            model_name="layawaypayment",
            name="reference_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="layawaypayment",
            name="reference_type",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.CreateModel(
            name="LayawayExtensionLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("old_expires_at", models.DateTimeField()),
                ("new_expires_at", models.DateTimeField()),
                ("reason", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="layaway_extensions", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "layaway",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="extensions", to="layaway.layaway"),
                ),
            ],
        ),
        migrations.CreateModel(
            name="LayawayLine",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("qty", models.DecimalField(decimal_places=2, max_digits=12)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("unit_cost", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("discount_pct", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "layaway",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="layaway.layaway"),
                ),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="catalog.product")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["layaway", "product"], name="layline_lay_prod_idx"),
                ]
            },
        ),
    ]
