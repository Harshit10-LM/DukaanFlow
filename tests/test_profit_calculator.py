from decimal import Decimal
import pytest
from app.services.profit_calculator import calculate, money

def test_profit_is_decimal_and_never_ai_math():
    r = calculate([{'name': 'Kurti', 'quantity': '2', 'selling_price': '650', 'unit_cost': '340', 'packaging_cost': '20'}], '40')
    assert r['subtotal'] == Decimal('1300.00')
    assert r['product_cost'] == Decimal('680.00')
    assert r['packaging_cost'] == Decimal('40.00')
    assert r['other_cost'] == Decimal('40.00')
    assert r['estimated_profit'] == Decimal('540.00')

def test_multi_variant_test_case_two_navy_kurtis():
    items = [
        {'name': 'Navy Kurti', 'variant': 'Medium', 'quantity': 1, 'selling_price': '650.00', 'unit_cost': '350.00', 'packaging_cost': '20.00'},
        {'name': 'Navy Kurti', 'variant': 'Large', 'quantity': 1, 'selling_price': '650.00', 'unit_cost': '350.00', 'packaging_cost': '20.00'},
    ]
    r = calculate(items, '0')
    assert r['subtotal'] == Decimal('1300.00')
    assert r['product_cost'] == Decimal('700.00')
    assert r['packaging_cost'] == Decimal('40.00')
    assert r['other_cost'] == Decimal('0.00')
    assert r['estimated_profit'] == Decimal('560.00')
    assert r['margin'] == Decimal('43.08')
    assert r['missing_costs'] == []
    assert items[0]['line_subtotal'] == '650.00'
    assert items[1]['line_subtotal'] == '650.00'

def test_missing_unit_cost_suppresses_profit_and_margin():
    r = calculate([
        {'name': 'Known Item', 'quantity': 1, 'selling_price': '500.00', 'unit_cost': '200.00', 'packaging_cost': '10.00'},
        {'name': 'Unknown Cost Item', 'quantity': 1, 'selling_price': '500.00', 'unit_cost': ''},
    ])
    assert r['subtotal'] == Decimal('1000.00')
    assert r['product_cost'] is None
    assert r['packaging_cost'] is None
    assert r['estimated_profit'] is None
    assert r['margin'] is None
    assert 'Unknown Cost Item' in r['missing_costs']

def test_missing_packaging_cost_defaults_to_zero():
    r = calculate([{'name': 'Item', 'quantity': 2, 'selling_price': '100', 'unit_cost': '40', 'packaging_cost': ''}])
    assert r['packaging_cost'] == Decimal('0.00')
    assert r['product_cost'] == Decimal('80.00')
    assert r['estimated_profit'] == Decimal('120.00')

def test_negative_values_rejected():
    with pytest.raises(ValueError):
        calculate([{'name': 'X', 'quantity': 1, 'selling_price': '-5', 'unit_cost': '2'}])
    with pytest.raises(ValueError):
        calculate([{'name': 'X', 'quantity': 1, 'selling_price': '5', 'unit_cost': '-2'}])
    with pytest.raises(ValueError):
        calculate([{'name': 'X', 'quantity': 1, 'selling_price': '5', 'unit_cost': '2'}], other_cost='-10')

def test_invalid_quantity_rejected():
    with pytest.raises(ValueError, match='positive quantity'):
        calculate([{'name': 'X', 'quantity': 0, 'selling_price': '10', 'unit_cost': '5'}])
    with pytest.raises(ValueError, match='positive quantity'):
        calculate([{'name': 'X', 'quantity': -1, 'selling_price': '10', 'unit_cost': '5'}])
    with pytest.raises(ValueError, match='positive quantity'):
        calculate([{'name': 'X', 'quantity': 'abc', 'selling_price': '10', 'unit_cost': '5'}])

def test_empty_order_items_rejected():
    with pytest.raises(ValueError, match='at least one line item'):
        calculate([])

def test_money_helper_formatting():
    assert money('650') == Decimal('650.00')
    assert money('650.5') == Decimal('650.50')
    assert money('1,250.75') == Decimal('1250.75')
    assert money('') == Decimal('0.00')
    assert money(None) == Decimal('0.00')
    with pytest.raises(ValueError):
        money('invalid-string')
