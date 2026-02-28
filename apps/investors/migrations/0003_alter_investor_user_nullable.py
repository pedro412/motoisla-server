from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("investors", "0002_investorassignment_investor_assignment_qty_assigned_gt_zero_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="investor",
            name="user",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="investor_profile",
                to="accounts.user",
            ),
        ),
    ]
