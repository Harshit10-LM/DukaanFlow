from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

P = Decimal('0.01')

def money(value):
    if value is None or str(value).strip() == '':
        return Decimal('0.00')
    try:
        v = Decimal(str(value).strip().replace(',', ''))
        if v < 0:
            raise ValueError
        return v.quantize(P, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Enter a non-negative monetary amount.')

def calculate(items, other_cost='0'):
    subtotal = product = packaging = Decimal('0')
    missing = []
    if not items:
        raise ValueError('Order must contain at least one line item.')

    for idx, item in enumerate(items):
        try:
            q = int(item.get('quantity', 0))
            if q <= 0:
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError('Each line item needs a positive quantity.')

        item_sp = item.get('selling_price')
        if item_sp is None or str(item_sp).strip() == '':
            raise ValueError('Each line item needs a verified selling price.')

        price = money(item_sp)
        line_sub = (q * price).quantize(P, rounding=ROUND_HALF_UP)
        subtotal += line_sub
        item['line_subtotal'] = str(line_sub)

        uc = item.get('unit_cost')
        if uc in (None, ''):
            missing.append(item.get('name') or f'Line {idx + 1}')
            item['line_product_cost'] = None
            item['line_packaging_cost'] = None
            continue

        unit_cost_val = money(uc)
        pkg_cost_val = money(item.get('packaging_cost', '0'))
        line_prod = (q * unit_cost_val).quantize(P, rounding=ROUND_HALF_UP)
        line_pkg = (q * pkg_cost_val).quantize(P, rounding=ROUND_HALF_UP)

        product += line_prod
        packaging += line_pkg
        item['line_product_cost'] = str(line_prod)
        item['line_packaging_cost'] = str(line_pkg)

    other = money(other_cost)
    profit = None if missing else (subtotal - product - packaging - other).quantize(P, rounding=ROUND_HALF_UP)
    margin = None
    if profit is not None and subtotal > 0:
        margin = ((profit / subtotal) * Decimal('100')).quantize(P, rounding=ROUND_HALF_UP)

    return {
        'subtotal': subtotal.quantize(P, rounding=ROUND_HALF_UP),
        'product_cost': product.quantize(P, rounding=ROUND_HALF_UP) if not missing else None,
        'packaging_cost': packaging.quantize(P, rounding=ROUND_HALF_UP) if not missing else None,
        'other_cost': other.quantize(P, rounding=ROUND_HALF_UP),
        'estimated_profit': profit,
        'margin': margin,
        'missing_costs': missing,
    }

