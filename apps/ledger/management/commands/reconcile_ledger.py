import sys
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum

from apps.investors.models import Investor, InvestorAssignment
from apps.ledger.services import current_balances
from apps.sales.models import Sale, SaleLineProfitability, SaleStatus


class Command(BaseCommand):
    help = "Verifica integridad del ledger de inversionistas (solo lectura, sin efectos secundarios)."

    def handle(self, *args, **options):
        mismatches = 0

        investors = list(Investor.objects.all())
        self.stdout.write(f"Verificando {len(investors)} inversionistas...")

        for inv in investors:
            balances = current_balances(inv)
            ledger_capital = balances["capital"]
            ledger_inventory = balances["inventory"]
            ledger_profit = balances["profit"]

            # Re-aggregate directly to compare (service uses same query, this is a double-check)
            from apps.ledger.models import LedgerEntry
            raw = inv.ledger_entries.aggregate(
                cap=Sum("capital_delta"),
                inv=Sum("inventory_delta"),
                pro=Sum("profit_delta"),
            )
            raw_capital = raw["cap"] or Decimal("0.00")
            raw_inventory = raw["inv"] or Decimal("0.00")
            raw_profit = raw["pro"] or Decimal("0.00")

            if (
                Decimal(str(ledger_capital)) != Decimal(str(raw_capital))
                or Decimal(str(ledger_inventory)) != Decimal(str(raw_inventory))
                or Decimal(str(ledger_profit)) != Decimal(str(raw_profit))
            ):
                mismatches += 1
                self.stdout.write(
                    f"  [MISMATCH] {inv.display_name} — "
                    f"capital: servicio=${ledger_capital} / raw=${raw_capital} | "
                    f"inventory: servicio=${ledger_inventory} / raw=${raw_inventory} | "
                    f"profit: servicio=${ledger_profit} / raw=${raw_profit}"
                )
            else:
                self.stdout.write(
                    f"  [OK] {inv.display_name} — "
                    f"capital: ${ledger_capital} / inventory: ${ledger_inventory} / profit: ${ledger_profit}"
                )

        assignments = list(InvestorAssignment.objects.select_related("investor", "product").all())
        self.stdout.write(f"Verificando {len(assignments)} asignaciones...")

        ok_count = 0
        for asgn in assignments:
            result = SaleLineProfitability.objects.filter(
                assignment=asgn,
                snapshot__sale__status=SaleStatus.CONFIRMED,
            ).aggregate(total=Sum("qty_consumed"))
            expected = result["total"] or Decimal("0.00")
            actual = Decimal(str(asgn.qty_sold))

            if actual != Decimal(str(expected)):
                mismatches += 1
                self.stdout.write(
                    f"  [MISMATCH] Asignación #{asgn.id} "
                    f"producto \"{asgn.product.name}\" ({asgn.investor.display_name}) — "
                    f"qty_sold esperado: {expected} / encontrado: {actual}"
                )
            else:
                ok_count += 1

        if ok_count:
            self.stdout.write(f"  [OK] {ok_count} asignaciones")

        if mismatches:
            self.stderr.write(f"Resultado: {mismatches} inconsistencias encontradas")
            sys.exit(1)
        else:
            self.stdout.write("Resultado: todo consistente ✓")
