# Generated manually for customer-linked sales and customer credit payments.

import django.db.models.deletion

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("layaway", "0004_customer_layawayline_layawayextensionlog_and_more"),
        ("sales", "0003_cardcommissionplan_payment_commission_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="sale",
            name="customer",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sales",
                to="layaway.customer",
            ),
        ),
        migrations.AlterField(
            model_name="payment",
            name="method",
            field=models.CharField(
                choices=[("CASH", "Cash"), ("CARD", "Card"), ("CUSTOMER_CREDIT", "Customer Credit")],
                max_length=20,
            ),
        ),
    ]
