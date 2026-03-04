from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from django.db.models import Count, Sum
from django.utils import timezone

from apps.expenses.models import Expense, ExpenseStatus
from apps.investors.models import InvestorAssignment
from apps.ledger.models import LedgerEntry, LedgerEntryType
from apps.sales.models import (
    LEGACY_CARD_TYPE_TO_RATE,
    PaymentMethod,
    ProfitabilityRateSource,
    Sale,
    SaleLine,
    SaleLineProfitability,
    SaleProfitabilitySnapshot,
    SaleStatus,
)

MONEY_QUANT = Decimal("0.01")
RATE_QUANT = Decimal("0.0001")

BASE_RATE = Decimal("0.1750")
MIN_RATE = Decimal("0.0800")
MAX_RATE = Decimal("0.3500")
MIN_SALES_AMOUNT = Decimal("50000.00")
MIN_SALES_COUNT = 20
INVESTOR_SHARE_RATE = Decimal("0.50")


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def rate(value: Decimal) -> Decimal:
    return Decimal(value).quantize(RATE_QUANT, rounding=ROUND_HALF_UP)


def clamp_rate(raw: Decimal) -> Decimal:
    return max(MIN_RATE, min(MAX_RATE, raw))


def allocate_proportionally(total: Decimal, weights: Iterable[Decimal]) -> list[Decimal]:
    total = money(total)
    weight_list = [Decimal(w) for w in weights]
    weight_sum = sum(weight_list, Decimal("0.00"))
    if total == Decimal("0.00") or weight_sum <= Decimal("0.00"):
        return [Decimal("0.00") for _ in weight_list]

    allocations = [Decimal("0.00") for _ in weight_list]
    non_zero_indexes = [idx for idx, value in enumerate(weight_list) if value > 0]
    if not non_zero_indexes:
        return allocations

    remaining = total
    for idx in non_zero_indexes[:-1]:
        allocated = money(total * (weight_list[idx] / weight_sum))
        allocations[idx] = allocated
        remaining -= allocated
    allocations[non_zero_indexes[-1]] = money(remaining)
    return allocations


def sale_commission_total(sale: Sale) -> Decimal:
    commission_total = Decimal("0.00")
    for payment in sale.payments.all():
        if payment.method != PaymentMethod.CARD:
            continue
        commission_rate = payment.commission_rate
        if commission_rate is None:
            commission_rate = LEGACY_CARD_TYPE_TO_RATE.get(payment.card_type, Decimal("0.00"))
        commission_total += payment.amount * commission_rate
    return money(commission_total)


@dataclass
class OperatingCostRateSnapshot:
    operating_cost_rate: Decimal
    rate_source: str
    calculated_at: datetime
    confirmed_sales_mtd: Decimal
    sales_count_mtd: int
    paid_expenses_mtd: Decimal


def current_operating_cost_rate_snapshot(*, now_dt: datetime | None = None) -> OperatingCostRateSnapshot:
    now_dt = now_dt or timezone.now()
    local_now = timezone.localtime(now_dt)
    month_start = local_now.date().replace(day=1)
    month_end = local_now.date()

    sales_mtd = Sale.objects.filter(
        status=SaleStatus.CONFIRMED,
        confirmed_at__date__gte=month_start,
        confirmed_at__date__lte=month_end,
    ).aggregate(total=Sum("total"), sales_count=Count("id"))
    paid_expenses_mtd = (
        Expense.objects.filter(
            status=ExpenseStatus.PAID,
            expense_date__gte=month_start,
            expense_date__lte=month_end,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    confirmed_sales_total = Decimal(str(sales_mtd["total"] or Decimal("0.00")))
    sales_count = int(sales_mtd["sales_count"] or 0)
    paid_expenses_total = Decimal(str(paid_expenses_mtd))

    if confirmed_sales_total <= Decimal("0.00") or confirmed_sales_total < MIN_SALES_AMOUNT or sales_count < MIN_SALES_COUNT:
        calculated_rate = BASE_RATE
        source = ProfitabilityRateSource.FALLBACK_BASE
    else:
        calculated_rate = clamp_rate(paid_expenses_total / confirmed_sales_total)
        source = ProfitabilityRateSource.MTD_REAL

    return OperatingCostRateSnapshot(
        operating_cost_rate=rate(calculated_rate),
        rate_source=source,
        calculated_at=local_now,
        confirmed_sales_mtd=money(confirmed_sales_total),
        sales_count_mtd=sales_count,
        paid_expenses_mtd=money(paid_expenses_total),
    )


@dataclass
class ChunkInput:
    sale_line: SaleLine
    qty: Decimal
    revenue: Decimal
    cogs: Decimal
    operating_cost: Decimal
    commission_cost: Decimal
    ownership: str
    assignment: InvestorAssignment | None = None


def _line_revenue(line: SaleLine) -> Decimal:
    gross = line.qty * line.unit_price
    discount = gross * line.discount_pct / Decimal("100.00")
    return money(gross - discount)


def _build_line_chunks(
    *,
    sale_line: SaleLine,
    line_revenue: Decimal,
    line_operating_cost: Decimal,
    line_commission_cost: Decimal,
    lock_assignments: bool,
) -> tuple[list[ChunkInput], list[InvestorAssignment]]:
    assignments_qs = InvestorAssignment.objects.filter(product=sale_line.product, qty_assigned__gt=0).order_by("created_at", "id")
    if lock_assignments:
        assignments_qs = assignments_qs.select_for_update()
    assignments = list(assignments_qs)

    chunks: list[ChunkInput] = []
    touched_assignments: list[InvestorAssignment] = []
    remaining_qty = Decimal(sale_line.qty)
    qty_weights: list[Decimal] = []

    for assignment in assignments:
        available = Decimal(assignment.qty_assigned) - Decimal(assignment.qty_sold)
        if available <= Decimal("0.00") or remaining_qty <= Decimal("0.00"):
            continue
        consumed = min(available, remaining_qty)
        remaining_qty -= consumed
        touched_assignments.append(assignment)
        qty_weights.append(consumed)
        chunks.append(
            ChunkInput(
                sale_line=sale_line,
                qty=consumed,
                revenue=Decimal("0.00"),
                cogs=money(Decimal(assignment.unit_cost) * consumed),
                operating_cost=Decimal("0.00"),
                commission_cost=Decimal("0.00"),
                ownership=SaleLineProfitability.Ownership.INVESTOR,
                assignment=assignment,
            )
        )

    if remaining_qty > Decimal("0.00"):
        qty_weights.append(remaining_qty)
        chunks.append(
            ChunkInput(
                sale_line=sale_line,
                qty=remaining_qty,
                revenue=Decimal("0.00"),
                cogs=money(Decimal(sale_line.unit_cost) * remaining_qty),
                operating_cost=Decimal("0.00"),
                commission_cost=Decimal("0.00"),
                ownership=SaleLineProfitability.Ownership.STORE,
            )
        )

    if not chunks:
        return chunks, touched_assignments

    revenue_alloc = allocate_proportionally(line_revenue, qty_weights)
    op_alloc = allocate_proportionally(line_operating_cost, qty_weights)
    comm_alloc = allocate_proportionally(line_commission_cost, qty_weights)
    for index, chunk in enumerate(chunks):
        chunk.revenue = money(revenue_alloc[index])
        chunk.operating_cost = money(op_alloc[index])
        chunk.commission_cost = money(comm_alloc[index])
    return chunks, touched_assignments


def build_sale_profitability_preview(*, lines: list[dict], payments: list[dict]) -> dict:
    sale_revenues = [money(line["qty"] * line["unit_price"] * (Decimal("1.00") - (line["discount_pct"] / Decimal("100.00")))) for line in lines]
    sale_revenue_total = money(sum(sale_revenues, Decimal("0.00")))

    commission_total = Decimal("0.00")
    for payment in payments:
        if payment["method"] != PaymentMethod.CARD:
            continue
        commission_rate = payment.get("commission_rate") or LEGACY_CARD_TYPE_TO_RATE.get(payment.get("card_type"), Decimal("0.00"))
        commission_total += Decimal(payment["amount"]) * Decimal(commission_rate or Decimal("0.00"))
    commission_total = money(commission_total)

    rate_snapshot = current_operating_cost_rate_snapshot()
    operating_cost_amount = money(sale_revenue_total * rate_snapshot.operating_cost_rate)
    line_operating_alloc = allocate_proportionally(operating_cost_amount, sale_revenues)
    line_commission_alloc = allocate_proportionally(commission_total, sale_revenues)

    preview_lines: list[dict] = []
    gross_profit_total = Decimal("0.00")
    net_profit_total = Decimal("0.00")
    investor_profit_total = Decimal("0.00")
    store_profit_total = Decimal("0.00")

    for index, line in enumerate(lines):
        line_revenue = sale_revenues[index]
        line_operating = line_operating_alloc[index]
        line_commission = line_commission_alloc[index]
        sale_line = line["sale_line"]

        chunks, _ = _build_line_chunks(
            sale_line=sale_line,
            line_revenue=line_revenue,
            line_operating_cost=line_operating,
            line_commission_cost=line_commission,
            lock_assignments=False,
        )
        for chunk in chunks:
            line_net_profit = money(chunk.revenue - chunk.cogs - chunk.operating_cost - chunk.commission_cost)
            if chunk.ownership == SaleLineProfitability.Ownership.INVESTOR:
                investor_share = money(max(Decimal("0.00"), line_net_profit * INVESTOR_SHARE_RATE))
            else:
                investor_share = Decimal("0.00")
            store_share = money(line_net_profit - investor_share)

            preview_lines.append(
                {
                    "product": str(chunk.sale_line.product_id),
                    "line_revenue": chunk.revenue,
                    "line_cogs": chunk.cogs,
                    "line_operating_cost": chunk.operating_cost,
                    "line_commission_cost": chunk.commission_cost,
                    "line_net_profit": line_net_profit,
                    "ownership": chunk.ownership,
                    "investor_id": str(chunk.assignment.investor_id) if chunk.assignment else None,
                    "investor_profit_share": investor_share,
                    "store_profit_share": store_share,
                }
            )

            gross_profit_total += money(chunk.revenue - chunk.cogs)
            net_profit_total += line_net_profit
            investor_profit_total += investor_share
            store_profit_total += store_share

    return {
        "operating_cost_rate_snapshot": rate_snapshot.operating_cost_rate,
        "operating_cost_rate_source": rate_snapshot.rate_source,
        "operating_cost_amount": money(operating_cost_amount),
        "commission_amount": money(commission_total),
        "gross_profit_total": money(gross_profit_total),
        "net_profit_total": money(net_profit_total),
        "investor_profit_total": money(investor_profit_total),
        "store_profit_total": money(store_profit_total),
        "lines": preview_lines,
    }


def apply_sale_profitability(*, sale: Sale) -> SaleProfitabilitySnapshot:
    line_items = list(sale.lines.select_related("product"))
    line_revenues = [_line_revenue(line) for line in line_items]
    sale_revenue_total = money(sum(line_revenues, Decimal("0.00")))
    commission_total = sale_commission_total(sale)

    rate_snapshot = current_operating_cost_rate_snapshot()
    operating_cost_amount = money(sale_revenue_total * rate_snapshot.operating_cost_rate)
    line_operating_alloc = allocate_proportionally(operating_cost_amount, line_revenues)
    line_commission_alloc = allocate_proportionally(commission_total, line_revenues)

    snapshot = SaleProfitabilitySnapshot.objects.create(
        sale=sale,
        operating_cost_rate_snapshot=rate_snapshot.operating_cost_rate,
        operating_cost_rate_source=rate_snapshot.rate_source,
        operating_cost_amount=money(operating_cost_amount),
        commission_amount=money(commission_total),
    )

    gross_profit_total = Decimal("0.00")
    net_profit_total = Decimal("0.00")
    investor_profit_total = Decimal("0.00")
    store_profit_total = Decimal("0.00")
    dirty_assignments: dict[str, InvestorAssignment] = {}

    for index, line in enumerate(line_items):
        chunks, touched = _build_line_chunks(
            sale_line=line,
            line_revenue=line_revenues[index],
            line_operating_cost=line_operating_alloc[index],
            line_commission_cost=line_commission_alloc[index],
            lock_assignments=True,
        )
        for assignment in touched:
            dirty_assignments[str(assignment.id)] = assignment

        for chunk in chunks:
            if chunk.assignment:
                chunk.assignment.qty_sold = money(Decimal(chunk.assignment.qty_sold) + Decimal(chunk.qty))

            line_net_profit = money(chunk.revenue - chunk.cogs - chunk.operating_cost - chunk.commission_cost)
            if chunk.ownership == SaleLineProfitability.Ownership.INVESTOR:
                investor_share = money(max(Decimal("0.00"), line_net_profit * INVESTOR_SHARE_RATE))
            else:
                investor_share = Decimal("0.00")
            store_share = money(line_net_profit - investor_share)

            SaleLineProfitability.objects.create(
                snapshot=snapshot,
                sale_line=line,
                product=line.product,
                assignment=chunk.assignment,
                investor=chunk.assignment.investor if chunk.assignment else None,
                ownership=chunk.ownership,
                qty_consumed=money(chunk.qty),
                line_revenue=money(chunk.revenue),
                line_cogs=money(chunk.cogs),
                line_operating_cost=money(chunk.operating_cost),
                line_commission_cost=money(chunk.commission_cost),
                line_net_profit=money(line_net_profit),
                investor_profit_share=money(investor_share),
                store_profit_share=money(store_share),
            )

            if chunk.assignment:
                LedgerEntry.objects.create(
                    investor=chunk.assignment.investor,
                    entry_type=LedgerEntryType.INVENTORY_TO_CAPITAL,
                    capital_delta=money(chunk.cogs),
                    inventory_delta=money(-chunk.cogs),
                    profit_delta=Decimal("0.00"),
                    reference_type="sale",
                    reference_id=str(sale.id),
                    note="Capital recovery",
                )
                if investor_share > Decimal("0.00"):
                    LedgerEntry.objects.create(
                        investor=chunk.assignment.investor,
                        entry_type=LedgerEntryType.PROFIT_SHARE,
                        capital_delta=Decimal("0.00"),
                        inventory_delta=Decimal("0.00"),
                        profit_delta=money(investor_share),
                        reference_type="sale",
                        reference_id=str(sale.id),
                        note="Profit share 50/50 (net)",
                    )

            gross_profit_total += money(chunk.revenue - chunk.cogs)
            net_profit_total += money(line_net_profit)
            investor_profit_total += money(investor_share)
            store_profit_total += money(store_share)

    if dirty_assignments:
        InvestorAssignment.objects.bulk_update(list(dirty_assignments.values()), ["qty_sold"])

    snapshot.gross_profit_total = money(gross_profit_total)
    snapshot.net_profit_total = money(net_profit_total)
    snapshot.investor_profit_total = money(investor_profit_total)
    snapshot.store_profit_total = money(store_profit_total)
    snapshot.save(
        update_fields=[
            "gross_profit_total",
            "net_profit_total",
            "investor_profit_total",
            "store_profit_total",
        ]
    )
    return snapshot


def revert_sale_profitability(*, sale: Sale) -> None:
    snapshot = getattr(sale, "profitability_snapshot", None)
    if not snapshot:
        return

    sale_lines = list(snapshot.lines.select_related("assignment", "investor"))
    dirty_assignments: dict[str, InvestorAssignment] = {}

    for line in sale_lines:
        if line.assignment:
            line.assignment.qty_sold = money(max(Decimal("0.00"), Decimal(line.assignment.qty_sold) - Decimal(line.qty_consumed)))
            dirty_assignments[str(line.assignment.id)] = line.assignment

    if dirty_assignments:
        InvestorAssignment.objects.bulk_update(list(dirty_assignments.values()), ["qty_sold"])

    ledger_entries = LedgerEntry.objects.filter(reference_type="sale", reference_id=str(sale.id))
    for entry in ledger_entries:
        LedgerEntry.objects.create(
            investor=entry.investor,
            entry_type=entry.entry_type,
            capital_delta=money(-entry.capital_delta),
            inventory_delta=money(-entry.inventory_delta),
            profit_delta=money(-entry.profit_delta),
            reference_type="sale_void",
            reference_id=str(sale.id),
            note=f"{entry.note or 'Sale reversal'} (void)",
        )
