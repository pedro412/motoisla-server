from decimal import Decimal, InvalidOperation

from apps.catalog.models import Product
from apps.imports.models import MatchStatus


def _to_decimal(value):
    if value is None:
        return None
    text = str(value).strip().replace("$", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_invoice_line(raw_line):
    line = raw_line.strip()
    if not line:
        return None

    delimiter = "|" if "|" in line else ","
    parts = [p.strip() for p in line.split(delimiter)]
    if len(parts) < 5:
        return {
            "sku": "",
            "name": line,
            "qty": None,
            "unit_cost": None,
            "unit_price": None,
            "match_status": MatchStatus.INVALID,
            "matched_product": None,
        }

    sku, name, qty_raw, unit_cost_raw, unit_price_raw = parts[:5]
    qty = _to_decimal(qty_raw)
    unit_cost = _to_decimal(unit_cost_raw)
    unit_price = _to_decimal(unit_price_raw)

    product = Product.objects.filter(sku=sku).first() if sku else None
    if not sku or qty is None or unit_cost is None:
        status = MatchStatus.INVALID
    elif product:
        status = MatchStatus.MATCHED_PRODUCT
    else:
        status = MatchStatus.NEW_PRODUCT

    return {
        "sku": sku,
        "name": name,
        "qty": qty,
        "unit_cost": unit_cost,
        "unit_price": unit_price,
        "match_status": status,
        "matched_product": product,
    }


def parse_invoice_text(raw_text, parser_key):
    normalized_text = (raw_text or "").replace("\\n", "\n")
    raw_lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]
    parsed_rows = []

    parser_kind = (parser_key or "").strip().lower()
    for raw_line in raw_lines:
        if raw_line.startswith("#"):
            continue

        line = raw_line
        if parser_kind == "pipe" and "|" not in line:
            line = line.replace(",", "|")
        elif parser_kind in {"csv", "comma"} and "," not in line:
            line = line.replace("|", ",")

        parsed = parse_invoice_line(line)
        if parsed is not None:
            parsed_rows.append((raw_line, parsed))
    return parsed_rows
