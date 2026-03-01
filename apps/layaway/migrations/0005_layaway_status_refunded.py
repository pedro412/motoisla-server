# Generated manually to reflect new REFUNDED layaway state.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("layaway", "0004_customer_layawayline_layawayextensionlog_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="layaway",
            name="status",
            field=models.CharField(
                choices=[
                    ("ACTIVE", "Active"),
                    ("SETTLED", "Settled"),
                    ("EXPIRED", "Expired"),
                    ("REFUNDED", "Refunded"),
                ],
                default="ACTIVE",
                max_length=16,
            ),
        ),
    ]
