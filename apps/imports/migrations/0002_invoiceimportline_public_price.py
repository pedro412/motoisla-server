from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("imports", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoiceimportline",
            name="public_price",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
    ]
