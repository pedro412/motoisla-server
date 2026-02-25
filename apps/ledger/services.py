from decimal import Decimal

from django.db.models import DecimalField, Sum
from django.db.models.functions import Coalesce

from apps.ledger.models import LedgerEntry, LedgerEntryType


def current_balances(investor):
    return investor.ledger_entries.aggregate(
        capital=Coalesce(Sum("capital_delta"), 0, output_field=DecimalField(max_digits=12, decimal_places=2)),
        inventory=Coalesce(Sum("inventory_delta"), 0, output_field=DecimalField(max_digits=12, decimal_places=2)),
        profit=Coalesce(Sum("profit_delta"), 0, output_field=DecimalField(max_digits=12, decimal_places=2)),
    )


def create_capital_deposit(*, investor, amount, reference_type, reference_id, note=""):
    amount = Decimal(amount).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValueError("El monto del deposito debe ser mayor a 0.")
    return LedgerEntry.objects.create(
        investor=investor,
        entry_type=LedgerEntryType.CAPITAL_DEPOSIT,
        capital_delta=amount,
        inventory_delta=Decimal("0.00"),
        profit_delta=Decimal("0.00"),
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
    )


def create_capital_withdrawal(*, investor, amount, reference_type, reference_id, note=""):
    amount = Decimal(amount).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValueError("El monto del retiro debe ser mayor a 0.")
    balances = current_balances(investor)
    if amount > balances["capital"]:
        raise ValueError("No hay capital liquido suficiente para retirar ese monto.")
    return LedgerEntry.objects.create(
        investor=investor,
        entry_type=LedgerEntryType.CAPITAL_WITHDRAWAL,
        capital_delta=-amount,
        inventory_delta=Decimal("0.00"),
        profit_delta=Decimal("0.00"),
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
    )


def create_reinvestment(*, investor, amount, reference_type, reference_id, note=""):
    amount = Decimal(amount).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValueError("El monto de reinversion debe ser mayor a 0.")
    balances = current_balances(investor)
    if amount > balances["profit"]:
        raise ValueError("No hay utilidad disponible suficiente para reinvertir ese monto.")

    LedgerEntry.objects.create(
        investor=investor,
        entry_type=LedgerEntryType.REINVESTMENT,
        capital_delta=amount,
        inventory_delta=Decimal("0.00"),
        profit_delta=-amount,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
    )
