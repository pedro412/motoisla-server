from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record_audit
from apps.inventory.models import InventoryMovement, MovementType
from apps.layaway.models import CustomerCredit, Layaway, LayawayStatus


class Command(BaseCommand):
    help = "Expira apartados vencidos y convierte lo abonado a saldo a favor."

    def handle(self, *args, **options):
        expired_count = 0
        queryset = (
            Layaway.objects.select_related("customer", "created_by")
            .prefetch_related("lines")
            .filter(status=LayawayStatus.ACTIVE, expires_at__lt=timezone.now())
        )
        for layaway in queryset:
            with transaction.atomic():
                locked = Layaway.objects.select_for_update().select_related("customer", "created_by").get(pk=layaway.pk)
                if locked.status != LayawayStatus.ACTIVE or locked.expires_at >= timezone.now():
                    continue
                locked.status = LayawayStatus.EXPIRED
                locked.save(update_fields=["status", "updated_at"])

                for line in locked.lines.all():
                    InventoryMovement.objects.create(
                        product=line.product,
                        movement_type=MovementType.RELEASED,
                        quantity_delta=line.qty,
                        reference_type="layaway_expire",
                        reference_id=str(locked.id),
                        note="Layaway expired release (auto)",
                        created_by=locked.created_by,
                    )

                if locked.customer_id and locked.amount_paid > 0:
                    credit, _ = CustomerCredit.objects.get_or_create(
                        customer=locked.customer,
                        defaults={
                            "customer_name": locked.customer.name,
                            "customer_phone": locked.customer.phone,
                            "balance": Decimal("0.00"),
                        },
                    )
                    credit.balance = (credit.balance + locked.amount_paid).quantize(Decimal("0.01"))
                    credit.save(update_fields=["balance", "updated_at", "customer_name", "customer_phone"])

                record_audit(
                    actor=locked.created_by,
                    action="layaway.expire.auto",
                    entity_type="layaway",
                    entity_id=locked.id,
                    payload={"credit_added": str(locked.amount_paid)},
                )
                expired_count += 1

        self.stdout.write(self.style.SUCCESS(f"Expired layaways: {expired_count}"))
