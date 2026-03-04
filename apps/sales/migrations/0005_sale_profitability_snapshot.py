# Generated manually for sale profitability snapshot support.

import django.db.models.deletion
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("investors", "0003_alter_investor_user_nullable"),
        ("sales", "0004_sale_customer_payment_customer_credit"),
    ]

    operations = [
        migrations.CreateModel(
            name="SaleProfitabilitySnapshot",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("operating_cost_rate_snapshot", models.DecimalField(decimal_places=4, max_digits=6)),
                (
                    "operating_cost_rate_source",
                    models.CharField(
                        choices=[("MTD_REAL", "MTD real"), ("FALLBACK_BASE", "Fallback base")],
                        max_length=24,
                    ),
                ),
                ("operating_cost_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("commission_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("gross_profit_total", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("net_profit_total", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("investor_profit_total", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("store_profit_total", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("calc_version", models.CharField(default="v1", max_length=16)),
                ("calculated_at", models.DateTimeField(auto_now_add=True)),
                (
                    "sale",
                    models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="profitability_snapshot", to="sales.sale"),
                ),
            ],
        ),
        migrations.CreateModel(
            name="SaleLineProfitability",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("ownership", models.CharField(choices=[("STORE", "Store"), ("INVESTOR", "Investor")], max_length=16)),
                ("qty_consumed", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("line_revenue", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("line_cogs", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("line_operating_cost", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("line_commission_cost", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("line_net_profit", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("investor_profit_share", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("store_profit_share", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                (
                    "assignment",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="investors.investorassignment"),
                ),
                (
                    "investor",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="investors.investor"),
                ),
                (
                    "product",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="catalog.product"),
                ),
                (
                    "sale_line",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="profitability_lines", to="sales.saleline"),
                ),
                (
                    "snapshot",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="sales.saleprofitabilitysnapshot"),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="saleprofitabilitysnapshot",
            index=models.Index(fields=["operating_cost_rate_source", "calculated_at"], name="saleprof_rate_source_idx"),
        ),
        migrations.AddIndex(
            model_name="saleprofitabilitysnapshot",
            index=models.Index(fields=["calculated_at"], name="saleprof_calc_at_idx"),
        ),
        migrations.AddIndex(
            model_name="salelineprofitability",
            index=models.Index(fields=["snapshot", "ownership"], name="salelineprof_snapshot_own_idx"),
        ),
        migrations.AddIndex(
            model_name="salelineprofitability",
            index=models.Index(fields=["investor", "ownership"], name="salelineprof_investor_own_idx"),
        ),
        migrations.AddIndex(
            model_name="salelineprofitability",
            index=models.Index(fields=["sale_line"], name="salelineprof_sale_line_idx"),
        ),
    ]
