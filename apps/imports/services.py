import re
from decimal import Decimal, InvalidOperation

from apps.catalog.models import Product
from apps.imports.models import MatchStatus

VAT_RATE = Decimal("1.16")
PUBLIC_PRICE_MARKUP = Decimal("1.30")

MYESA_ITEM_RE = re.compile(r"^\*\*\s*([A-Z0-9-]+)\s+([0-9]+(?:[.,][0-9]+)?)\s+\S+\s+(.+)$")
MYESA_PRICE_RE = re.compile(r"^\s*([0-9][0-9,]*\.[0-9]{2})\s+([0-9][0-9,]*\.[0-9]{2})\s*$")


def _to_decimal(value):
    if value is None:
        return None
    text = str(value).strip().replace("$", "").replace(" ", "")
    if not text:
        return None

    normalized = text.replace(",", "")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _quantize(amount):
    if amount is None:
        return None
    return amount.quantize(Decimal("0.01"))


def _compute_public_price(unit_cost):
    if unit_cost is None:
        return None
    return _quantize(unit_cost * VAT_RATE * PUBLIC_PRICE_MARKUP)


def _resolve_match(sku):
    if not sku:
        return None, MatchStatus.INVALID

    normalized_sku = sku.strip().upper()
    product = Product.objects.filter(sku=normalized_sku).first()
    if product:
        return product, MatchStatus.MATCHED_PRODUCT
    return None, MatchStatus.NEW_PRODUCT


def _build_parsed_row(sku, name, qty, unit_cost, unit_price):
    normalized_sku = (sku or "").strip().upper()
    qty_value = _to_decimal(qty)
    unit_cost_value = _to_decimal(unit_cost)
    unit_price_value = _to_decimal(unit_price)

    if unit_price_value is None and unit_cost_value is not None:
        unit_price_value = _quantize(unit_cost_value * VAT_RATE)

    product, status = _resolve_match(normalized_sku)
    if not normalized_sku or qty_value is None or unit_cost_value is None:
        status = MatchStatus.INVALID

    return {
        "sku": normalized_sku,
        "name": (name or "").strip(),
        "qty": qty_value,
        "unit_cost": unit_cost_value,
        "unit_price": unit_price_value,
        "public_price": _compute_public_price(unit_cost_value),
        "match_status": status,
        "matched_product": product,
    }


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
            "public_price": None,
            "match_status": MatchStatus.INVALID,
            "matched_product": None,
        }

    sku, name, qty_raw, unit_cost_raw, unit_price_raw = parts[:5]
    return _build_parsed_row(sku, name, qty_raw, unit_cost_raw, unit_price_raw)


def parse_myesa_text(raw_text):
    lines = [line.strip() for line in (raw_text or "").replace("\\n", "\n").splitlines() if line.strip()]
    parsed_rows = []
    index = 0

    while index < len(lines):
        line = lines[index]
        match = MYESA_ITEM_RE.match(line)
        if not match:
            index += 1
            continue

        sku = match.group(1).strip().upper()
        qty = match.group(2).strip()
        name = match.group(3).strip()

        unit_cost = None
        line_total = None
        scan = index + 1
        while scan < len(lines):
            candidate = lines[scan]
            if MYESA_ITEM_RE.match(candidate):
                break
            price_match = MYESA_PRICE_RE.match(candidate)
            if price_match:
                unit_cost = price_match.group(1)
                line_total = price_match.group(2)
            scan += 1

        parsed = _build_parsed_row(sku, name, qty, unit_cost, None)
        if parsed["unit_cost"] is None and line_total is not None and parsed["qty"]:
            total_value = _to_decimal(line_total)
            if total_value is not None and parsed["qty"] > 0:
                parsed["unit_cost"] = _quantize(total_value / parsed["qty"])
                parsed["unit_price"] = _quantize(parsed["unit_cost"] * VAT_RATE)
                parsed["public_price"] = _compute_public_price(parsed["unit_cost"])

        parsed_rows.append((line, parsed))
        index = scan

    return parsed_rows


def parse_invoice_text(raw_text, parser_key):
    normalized_text = (raw_text or "").replace("\\n", "\n")
    parser_kind = (parser_key or "").strip().lower()

    if parser_kind == "myesa":
        return parse_myesa_text(normalized_text)

    raw_lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]
    parsed_rows = []

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
