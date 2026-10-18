import json
from decimal import Decimal
import pytest
from app.services.gemma_service import GemmaService

def login(client, email='demo@dukaanflow.test', password='DemoPass123'):
    return client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)

def test_health(client):
    r = client.get('/health')
    assert r.status_code == 200
    assert r.json['status'] == 'ok'

def test_auth_and_protected_routes(client):
    assert client.get('/').status_code == 302
    assert client.get('/orders/').status_code == 302
    assert client.get('/products/').status_code == 302
    login(client)
    assert client.get('/').status_code == 200
    assert client.get('/orders/').status_code == 200
    assert client.get('/products/').status_code == 200

def test_registration_validation(client):
    r = client.post('/register', data={'email': 'bad', 'password': '123', 'business_name': ''}, follow_redirects=True)
    assert b'Use a business name' in r.data
    # Successful registration
    r2 = client.post('/register', data={'email': 'newuser@dukaanflow.test', 'password': 'Password123!', 'business_name': 'New Boutique'}, follow_redirects=True)
    assert r2.status_code == 200
    assert b'Dashboard' in r2.data or b'Overview' in r2.data

def test_product_crud_and_monetary_validation(client):
    login(client)
    # Rejects missing price
    r_bad = client.post('/products/', data={'name': 'Dress', 'selling_price': ''}, follow_redirects=True)
    assert b'Selling price is required' in r_bad.data

    # Rejects negative price
    r_neg = client.post('/products/', data={'name': 'Dress', 'selling_price': '-50'}, follow_redirects=True)
    assert b'non-negative monetary amount' in r_neg.data

    # Valid product
    r_ok = client.post('/products/', data={'name': 'Silk Scarf', 'selling_price': '499.00', 'unit_cost': '200.00', 'packaging_cost': '15.00', 'stock': '10'}, follow_redirects=True)
    assert b'Product added.' in r_ok.data
    assert b'Silk Scarf' in r_ok.data

def test_multi_item_order_creation_and_persistence(client, app):
    login(client)
    # Post multi-line order with Navy Kurti (Medium and Large)
    order_payload = {
        'customer_name': 'Pooja Sharma',
        'customer_contact': '+91 9876543210',
        'delivery_date': 'by Friday, 24 Oct',
        'delivery_address': 'Flat 402, Lotus Towers, Pune',
        'payment_terms': '50% advance, balance on delivery',
        'item_name': ['Navy Kurti', 'Navy Kurti'],
        'variant': ['Medium', 'Large'],
        'quantity': ['1', '1'],
        'selling_price': ['650.00', '650.00'],
        'unit_cost': ['350.00', '350.00'],
        'packaging_cost': ['20.00', '20.00'],
        'other_cost': '0.00',
        'status': 'Draft',
        'reply_draft': 'Thanks Pooja! Order for 2 Navy Kurtis confirmed.'
    }
    r = client.post('/orders/new', data=order_payload, follow_redirects=True)
    assert r.status_code == 200
    assert b'Order saved as Draft.' in r.data
    assert b'Pooja Sharma' in r.data
    assert b'Medium' in r.data
    assert b'Large' in r.data
    assert b'by Friday, 24 Oct' in r.data
    assert b'1300.00' in r.data
    assert b'560.00' in r.data
    assert b'43.08%' in r.data

def test_order_edit_multi_items_and_status_transitions(client, app):
    login(client)
    # Create order first
    repo = app.extensions['repo']
    # Get user
    user = repo.by_email('demo@dukaanflow.test')
    order = repo.create_order(user['_id'], {
        'customer_name': 'Ravi Kumar',
        'items': [
            {'name': 'Navy Kurti', 'variant': 'M', 'quantity': 1, 'selling_price': '650.00', 'unit_cost': '350.00', 'packaging_cost': '20.00'}
        ],
        'other_cost': '0.00',
        'status': 'Draft',
        'calculation': {'subtotal': '650.00', 'estimated_profit': '280.00'}
    })
    order_id = str(order['_id'])

    # Valid status change: Draft -> Needs confirmation
    edit_payload = {
        'customer_name': 'Ravi Kumar',
        'item_name': ['Navy Kurti', 'Navy Kurti'],
        'variant': ['M', 'L'],
        'quantity': ['1', '2'],
        'selling_price': ['650.00', '650.00'],
        'unit_cost': ['350.00', '350.00'],
        'packaging_cost': ['20.00', '20.00'],
        'other_cost': '10.00',
        'status': 'Needs confirmation'
    }
    r_edit = client.post(f'/orders/{order_id}', data=edit_payload, follow_redirects=True)
    assert r_edit.status_code == 200
    assert b'Order updated.' in r_edit.data
    assert b'Needs confirmation' in r_edit.data

    # Check updated calculation in repo
    updated = repo.get_order(user['_id'], order_id)
    assert len(updated['items']) == 2
    assert updated['calculation']['subtotal'] == '1950.00'

    # Disallowed status transition (Needs confirmation -> Delivered directly)
    r_bad_status = client.post(f'/orders/{order_id}', data={**edit_payload, 'status': 'Delivered'}, follow_redirects=True)
    assert b'status transition is not allowed' in r_bad_status.data

def test_cross_user_isolation(client, app):
    repo = app.extensions['repo']
    # User 1
    u1 = repo.create_user('seller1@test.com', 'Pass12345', 'Boutique 1')
    p1 = repo.create_product(u1['_id'], {'name': 'Private Kurti', 'selling_price': '999.00', 'unit_cost': '500.00', 'packaging_cost': '20.00'})
    o1 = repo.create_order(u1['_id'], {
        'customer_name': 'Private Buyer',
        'items': [{'name': 'Private Kurti', 'quantity': 1, 'selling_price': '999.00'}],
        'calculation': {'subtotal': '999.00'}
    })

    # User 2
    u2 = repo.create_user('seller2@test.com', 'Pass12345', 'Boutique 2')
    login(client, 'seller2@test.com', 'Pass12345')

    # User 2 attempts to view User 1's order
    r_order = client.get(f"/orders/{str(o1['_id'])}")
    assert r_order.status_code == 404

    # User 2 attempts to edit User 1's order
    r_edit = client.post(f"/orders/{str(o1['_id'])}", data={'customer_name': 'Hacked', 'item_name': 'X', 'selling_price': '10'})
    assert r_edit.status_code == 404

    # User 2 attempts to print invoice of User 1's order
    r_inv = client.get(f"/orders/{str(o1['_id'])}/invoice")
    assert r_inv.status_code == 404

    # User 2 attempts to delete User 1's product
    r_del_prod = client.post(f"/products/{str(p1['_id'])}/delete")
    assert r_del_prod.status_code == 404

def test_legacy_single_item_compatibility(client, app):
    login(client)
    repo = app.extensions['repo']
    user = repo.by_email('demo@dukaanflow.test')
    # Save an order with a single item (legacy format without list)
    legacy_order = repo.create_order(user['_id'], {
        'customer_name': 'Legacy Customer',
        'item': {'name': 'Vintage Saree', 'quantity': 1, 'selling_price': '1500.00'},
        'calculation': {'subtotal': '1500.00'}
    })
    order_id = str(legacy_order['_id'])

    # Detail page renders safely
    r_detail = client.get(f'/orders/{order_id}')
    assert r_detail.status_code == 200
    assert b'Legacy Customer' in r_detail.data
    assert b'Vintage Saree' in r_detail.data

    # Orders list renders safely
    r_list = client.get('/orders/')
    assert r_list.status_code == 200
    assert b'Legacy Customer' in r_list.data

def test_catalogue_auto_matching_in_extract(client, app, monkeypatch):
    login(client)
    repo = app.extensions['repo']
    user = repo.by_email('demo@dukaanflow.test')
    # Ensure Navy Kurti is in catalogue with known prices
    repo.create_product(user['_id'], {
        'name': 'Navy Kurti',
        'selling_price': '650.00',
        'unit_cost': '350.00',
        'packaging_cost': '20.00'
    })

    # Mock Gemma extraction returning 2 kurtis
    mock_extraction = {
        'customer_name': 'Meena',
        'customer_contact': '9898989898',
        'items': [
            {'product_name': 'Navy Kurti', 'variant': 'medium', 'quantity': 1, 'quoted_unit_price': '650.00', 'price_needs_verification': False},
            {'product_name': 'Navy Kurti', 'variant': 'large', 'quantity': 1, 'quoted_unit_price': '650.00', 'price_needs_verification': False}
        ],
        'delivery_request_text': 'Friday',
        'delivery_address': 'Sector 15, Chandigarh',
        'payment_terms': '50% advance',
        'stated_advance_amount': None,
        'notes': None,
        'missing_fields': [],
        'ambiguous_fields': [],
        'clarification_questions': [],
        'customer_reply_draft': 'Thanks Meena!'
    }

    monkeypatch.setattr(GemmaService, 'extract', lambda self, msg, cat: mock_extraction)

    r = client.post('/orders/extract', data={'original_message': 'Two navy kurtis M and L'}, follow_redirects=True)
    assert r.status_code == 200
    # Both lines rendered
    assert b'Catalogue matched: Navy Kurti' in r.data
    assert b'350.00' in r.data
    assert b'20.00' in r.data

def test_invoice_renders_line_totals_correctly(client, app):
    login(client)
    repo = app.extensions['repo']
    user = repo.by_email('demo@dukaanflow.test')
    order = repo.create_order(user['_id'], {
        'customer_name': 'Anil Kapoor',
        'items': [
            {'name': 'Scarf', 'variant': 'Red', 'quantity': 2, 'selling_price': '200.00', 'line_subtotal': '400.00'},
            {'name': 'Kurti', 'variant': 'Blue', 'quantity': 1, 'selling_price': '600.00', 'line_subtotal': '600.00'}
        ],
        'calculation': {'subtotal': '1000.00', 'other_cost': '0.00'},
        'status': 'Confirmed'
    })
    r = client.get(f"/orders/{str(order['_id'])}/invoice")
    assert r.status_code == 200
    assert b'Anil Kapoor' in r.data
    assert b'400.00' in r.data
    assert b'600.00' in r.data
    assert b'1000.00' in r.data

def test_speak_route_handles_unconfigured_voice_gracefully(client, app):
    login(client)
    repo = app.extensions['repo']
    user = repo.by_email('demo@dukaanflow.test')
    order = repo.create_order(user['_id'], {
        'customer_name': 'Test User',
        'items': [{'name': 'Item 1', 'quantity': 1, 'selling_price': '100.00'}],
        'reply_draft': 'Hello customer',
        'status': 'Draft'
    })
    order_id = str(order['_id'])

    # Standard browser post should redirect back with flash message without crash
    r = client.post(f'/orders/{order_id}/speak', follow_redirects=True)
    assert r.status_code == 200
    assert b'ElevenLabs' in r.data or b'voice' in r.data.lower()

def test_order_save_from_extract_page(client, app, monkeypatch):
    login(client)
    # 1. Post message to /orders/extract
    msg = 'Hi, I need two navy kurtis, one medium and one large. The price is ₹650 each, right? Can you deliver by Friday? I will pay half now and the rest on delivery.'
    r_extract = client.post('/orders/extract', data={'original_message': msg, 'is_extract_action': '1'})
    assert r_extract.status_code == 200
    # Verify the form has action="/orders/new"
    assert b'action="/orders/new"' in r_extract.data
    assert b'Save order for review' in r_extract.data
    assert b'delivery_date' in r_extract.data

    # 2. Click Save order for review (submits to /orders/new)
    save_payload = {
        'submission_token': 'token-extract-save-1',
        'original_message': msg,
        'customer_name': 'Asha Verma',
        'customer_contact': '+91 9876543210',
        'delivery_date': 'by Friday',
        'delivery_address': 'Flat 101, Pune',
        'payment_terms': '50% advance, balance on delivery',
        'reply_draft': 'Confirmed! Thanks Asha.',
        'item_name': ['Navy Kurti', 'Navy Kurti'],
        'variant': ['Medium', 'Large'],
        'quantity': ['1', '1'],
        'selling_price': ['650.00', '650.00'],
        'unit_cost': ['340.00', '340.00'],
        'packaging_cost': ['20.00', '20.00'],
        'other_cost': '0.00',
        'status': 'Draft',
    }
    r_save = client.post('/orders/new', data=save_payload, follow_redirects=True)
    assert r_save.status_code == 200
    assert b'Order saved as Draft.' in r_save.data
    assert b'Asha Verma' in r_save.data
    assert b'Medium' in r_save.data
    assert b'Large' in r_save.data
    assert b'by Friday' in r_save.data
    assert b'1300.00' in r_save.data

    # 3. Fallback direct post to /orders/extract with item_name also works safely
    save_fallback = {
        'submission_token': 'token-extract-save-2',
        'original_message': msg,
        'customer_name': 'Fallback User',
        'customer_contact': '+91 9999988888',
        'item_name': ['Navy Kurti'],
        'variant': ['Small'],
        'quantity': ['1'],
        'selling_price': ['650.00'],
        'status': 'Draft',
    }
    r_fallback = client.post('/orders/extract', data=save_fallback, follow_redirects=True)
    assert r_fallback.status_code == 200
    assert b'Order saved as Draft.' in r_fallback.data
    assert b'Fallback User' in r_fallback.data

def test_order_save_invalid_data_and_preservation(client):
    login(client)
    # Missing selling price
    bad_payload = {
        'customer_name': 'Incomplete Customer',
        'customer_contact': '+91 9999900000',
        'delivery_date': 'Next Monday',
        'delivery_address': 'Sector 21, Noida',
        'item_name': ['Silk Scarf'],
        'variant': ['Blue'],
        'quantity': ['2'],
        'selling_price': [''],
    }
    r = client.post('/orders/new', data=bad_payload, follow_redirects=True)
    assert r.status_code == 200
    assert b'Selling price is required' in r.data
    # Verify input preservation
    assert b'Incomplete Customer' in r.data
    assert b'+91 9999900000' in r.data
    assert b'Next Monday' in r.data
    assert b'Sector 21, Noida' in r.data
    assert b'Silk Scarf' in r.data

    # Invalid negative quantity
    bad_qty_payload = {
        'customer_name': 'Bad Qty Customer',
        'item_name': ['Silk Scarf'],
        'quantity': ['-3'],
        'selling_price': ['400.00'],
    }
    r_qty = client.post('/orders/new', data=bad_qty_payload, follow_redirects=True)
    assert r_qty.status_code == 200
    assert b'Invalid quantity' in r_qty.data or b'must be at least 1' in r_qty.data or b'positive quantity' in r_qty.data
    assert b'Bad Qty Customer' in r_qty.data

def test_order_save_insufficient_stock(client, app):
    login(client)
    # 'Navy Kurti' seeded stock is 12
    # 1. Single line exceeding stock
    single_exceed = {
        'customer_name': 'Bulk Buyer',
        'item_name': ['Navy Kurti'],
        'variant': ['M'],
        'quantity': ['15'],
        'selling_price': ['650.00'],
    }
    r1 = client.post('/orders/new', data=single_exceed, follow_redirects=True)
    assert r1.status_code == 200
    assert b'Insufficient stock for' in r1.data
    assert b'Navy Kurti' in r1.data
    assert b'Available: 12, requested: 15' in r1.data
    # Preserves entered name
    assert b'Bulk Buyer' in r1.data

    # 2. Multi-variant sum exceeding stock (8 + 5 = 13 > 12)
    multi_exceed = {
        'customer_name': 'Split Bulk Buyer',
        'item_name': ['Navy Kurti', 'Navy Kurti'],
        'variant': ['Medium', 'Large'],
        'quantity': ['8', '5'],
        'selling_price': ['650.00', '650.00'],
    }
    r2 = client.post('/orders/new', data=multi_exceed, follow_redirects=True)
    assert r2.status_code == 200
    assert b'Insufficient stock for' in r2.data
    assert b'Navy Kurti' in r2.data
    assert b'Available: 12, requested: 13' in r2.data

def test_order_save_duplicate_submission_prevention(client, app):
    login(client)
    repo = app.extensions['repo']
    user = repo.by_email('demo@dukaanflow.test')
    orders_count_before = len(repo.list_orders(user['_id']))

    token = 'dup-token-unique-123'
    payload = {
        'submission_token': token,
        'customer_name': 'Once Only Customer',
        'item_name': ['Navy Kurti'],
        'variant': ['L'],
        'quantity': ['1'],
        'selling_price': ['650.00'],
        'status': 'Draft'
    }

    # First submission -> creates order
    r1 = client.post('/orders/new', data=payload, follow_redirects=True)
    assert r1.status_code == 200
    assert b'Order saved as Draft.' in r1.data
    orders_count_after_first = len(repo.list_orders(user['_id']))
    assert orders_count_after_first == orders_count_before + 1

    # Second submission with the exact same token -> does NOT create a duplicate
    r2 = client.post('/orders/new', data=payload, follow_redirects=True)
    assert r2.status_code == 200
    assert b'This order has already been saved.' in r2.data
    orders_count_after_second = len(repo.list_orders(user['_id']))
    assert orders_count_after_second == orders_count_after_first

def test_order_save_unauthorized_access(client):
    # Unauthenticated client attempting to create an order
    r = client.post('/orders/new', data={'customer_name': 'Hacker'}, follow_redirects=False)
    assert r.status_code == 302
    assert '/login' in r.headers['Location']

def test_order_save_database_failure(client, app, monkeypatch):
    login(client)
    repo = app.extensions['repo']

    def failing_create_order(uid, d):
        raise RuntimeError('Simulated database connection crash')

    monkeypatch.setattr(repo, 'create_order', failing_create_order)

    payload = {
        'customer_name': 'Unlucky Customer',
        'item_name': ['Navy Kurti'],
        'variant': ['M'],
        'quantity': ['1'],
        'selling_price': ['650.00'],
    }
    r = client.post('/orders/new', data=payload, follow_redirects=True)
    assert r.status_code == 200
    assert b'Database error while saving order. Please try again.' in r.data
    assert b'Order saved' not in r.data
    # Preserves entered information
    assert b'Unlucky Customer' in r.data

