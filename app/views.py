import uuid
from decimal import Decimal, InvalidOperation
from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, abort, jsonify, Response, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from pymongo.errors import DuplicateKeyError
from .models import User
from .services.profit_calculator import calculate, money
from .services.gemma_service import GemmaService, GemmaError
from .services.elevenlabs_service import ElevenLabsService

auth = Blueprint('auth', __name__)
dashboard = Blueprint('dashboard', __name__)
products = Blueprint('products', __name__, url_prefix='/products')
orders = Blueprint('orders', __name__, url_prefix='/orders')
integrations = Blueprint('integrations', __name__, url_prefix='/settings')

def repo():
    return current_app.extensions['repo']

def price(v, required=False):
    if required and not str(v).strip():
        raise ValueError('Selling price is required.')
    if not str(v).strip():
        return ''
    return str(money(v))

def product_data(form):
    name = form.get('name', '').strip()
    if not name:
        raise ValueError('Product name is required.')
    return {
        'name': name,
        'sku': form.get('sku', '').strip(),
        'description': form.get('description', '').strip(),
        'variant_info': form.get('variant_info', '').strip(),
        'selling_price': price(form.get('selling_price'), True),
        'unit_cost': price(form.get('unit_cost')),
        'packaging_cost': price(form.get('packaging_cost')),
        'stock': form.get('stock', '').strip(),
    }

def match_catalogue_product(item_name, user_products):
    """Confidently match an extracted item against the seller's product catalogue."""
    if not item_name or not user_products:
        return None
    name_clean = item_name.strip().lower()
    # 1. Exact match
    for p in user_products:
        if p.get('name', '').strip().lower() == name_clean:
            return p
    # 2. Substring match (e.g. 'Navy Kurti' inside 'Navy Kurti Dress')
    for p in user_products:
        p_name = p.get('name', '').strip().lower()
        if p_name and (p_name in name_clean or name_clean in p_name):
            return p
    return None

def preserve_order_from_form(form):
    """Preserve entered order fields so nothing is lost if validation fails."""
    def _list(k):
        if hasattr(form, 'getlist'):
            res = form.getlist(k)
            if res:
                return res
        v = form.get(k)
        if isinstance(v, list):
            return v
        if v is not None and str(v).strip() != '':
            return [v]
        return []

    names = _list('item_name')
    variants = _list('variant')
    quantities = _list('quantity')
    selling_prices = _list('selling_price')
    unit_costs = _list('unit_cost')
    packaging_costs = _list('packaging_cost')
    product_ids = _list('product_id')
    quoted_prices = _list('quoted_price')

    count = max(len(names), len(variants), len(quantities), len(selling_prices), len(unit_costs))
    items = []
    for i in range(count):
        items.append({
            'name': names[i] if i < len(names) else '',
            'variant': variants[i] if i < len(variants) else '',
            'quantity': quantities[i] if i < len(quantities) else 1,
            'selling_price': selling_prices[i] if i < len(selling_prices) else '',
            'unit_cost': unit_costs[i] if i < len(unit_costs) else '',
            'packaging_cost': packaging_costs[i] if i < len(packaging_costs) else '0.00',
            'product_id': product_ids[i] if i < len(product_ids) else '',
            'quoted_price': quoted_prices[i] if i < len(quoted_prices) else '',
        })

    return {
        'customer_name': form.get('customer_name', '').strip(),
        'customer_contact': form.get('customer_contact', '').strip(),
        'delivery_address': form.get('delivery_address', '').strip(),
        'delivery_date': form.get('delivery_date', '').strip() or form.get('delivery_request_text', '').strip(),
        'payment_terms': form.get('payment_terms', '').strip(),
        'original_message': form.get('original_message', '').strip(),
        'reply_draft': form.get('reply_draft', '').strip(),
        'status': form.get('status', 'Draft'),
        'other_cost': form.get('other_cost', '0.00'),
        'items': items,
    }

def parse_order_items(form, user_products=None):
    """Parse multiple line items from form data with support for both multi-input and single-input formats.
    Validates names, positive integer quantities, selling prices, retrieves trusted catalogue data where
    omitted, and checks inventory stock for all matched items.
    """
    def _list(k):
        if hasattr(form, 'getlist'):
            res = form.getlist(k)
            if res:
                return res
        v = form.get(k)
        if isinstance(v, list):
            return v
        if v is not None and str(v).strip() != '':
            return [v]
        return []

    names = _list('item_name')
    variants = _list('variant')
    quantities = _list('quantity')
    selling_prices = _list('selling_price')
    unit_costs = _list('unit_cost')
    packaging_costs = _list('packaging_cost')
    product_ids = _list('product_id')
    quoted_prices = _list('quoted_price')

    count = max(len(names), len(variants), len(quantities), len(selling_prices), len(unit_costs))
    items = []

    prod_by_id = {}
    if user_products:
        prod_by_id = {str(p['_id']): p for p in user_products if p.get('_id')}

    for idx in range(count):
        name = names[idx].strip() if idx < len(names) else ''
        if not name:
            continue
        variant = variants[idx].strip() if idx < len(variants) else ''
        qty_str = str(quantities[idx]).strip() if idx < len(quantities) else '1'
        try:
            qty = int(qty_str)
            if qty < 1:
                raise ValueError(f'Quantity for "{name}" must be at least 1.')
        except (ValueError, TypeError):
            raise ValueError(f'Invalid quantity "{qty_str}" for item "{name}".')

        sp = selling_prices[idx].strip() if idx < len(selling_prices) else ''
        uc = unit_costs[idx].strip() if idx < len(unit_costs) else ''
        pc = packaging_costs[idx].strip() if idx < len(packaging_costs) else ''
        pid = product_ids[idx].strip() if idx < len(product_ids) else ''
        qp = quoted_prices[idx].strip() if idx < len(quoted_prices) else ''

        # Match with catalogue to retrieve trusted defaults
        matched = None
        if user_products:
            if pid and pid in prod_by_id:
                matched = prod_by_id[pid]
            else:
                matched = match_catalogue_product(name, user_products)
                if matched:
                    pid = str(matched.get('_id', ''))

            if matched:
                if not uc and matched.get('unit_cost'):
                    uc = str(matched['unit_cost'])
                if not pc and matched.get('packaging_cost'):
                    pc = str(matched['packaging_cost'])
                if not sp and matched.get('selling_price'):
                    sp = str(matched['selling_price'])

        if not sp:
            raise ValueError(f'Selling price is required for item "{name}".')

        sp_clean = str(money(sp))
        uc_clean = str(money(uc)) if uc else ''
        pc_clean = str(money(pc)) if pc else '0.00'
        qp_clean = str(money(qp)) if qp else ''

        items.append({
            'name': name,
            'variant': variant,
            'quantity': qty,
            'selling_price': sp_clean,
            'unit_cost': uc_clean,
            'packaging_cost': pc_clean,
            'product_id': pid or None,
            'quoted_price': qp_clean or None,
        })

    # Legacy or single-field fallback
    if not items:
        name = form.get('item_name', '').strip()
        if name:
            sp = form.get('selling_price', '').strip()
            uc = form.get('unit_cost', '').strip()
            pc = form.get('packaging_cost', '').strip()
            pid = form.get('product_id', '').strip()
            qp = form.get('quoted_price', '').strip()

            matched = None
            if user_products:
                if pid and pid in prod_by_id:
                    matched = prod_by_id[pid]
                else:
                    matched = match_catalogue_product(name, user_products)
                    if matched:
                        pid = str(matched.get('_id', ''))

                if matched:
                    if not uc and matched.get('unit_cost'):
                        uc = str(matched['unit_cost'])
                    if not pc and matched.get('packaging_cost'):
                        pc = str(matched['packaging_cost'])
                    if not sp and matched.get('selling_price'):
                        sp = str(matched['selling_price'])

            if not sp:
                raise ValueError(f'Selling price is required for item "{name}".')
            try:
                qty = max(1, int(form.get('quantity', '1')))
            except (ValueError, TypeError):
                qty = 1
            items.append({
                'name': name,
                'variant': form.get('variant', '').strip(),
                'quantity': qty,
                'selling_price': str(money(sp)),
                'unit_cost': str(money(uc)) if uc else '',
                'packaging_cost': str(money(pc)) if pc else '0.00',
                'product_id': pid or None,
                'quoted_price': qp or None,
            })

    if not items:
        raise ValueError('An order must contain at least one valid line item with a name and selling price.')

    # Inventory stock verification
    if user_products:
        product_quantities = {}
        for it in items:
            m_id = it.get('product_id')
            matched_prod = prod_by_id.get(m_id) if m_id else match_catalogue_product(it['name'], user_products)
            if matched_prod:
                target_id = str(matched_prod.get('_id'))
                product_quantities[target_id] = product_quantities.get(target_id, 0) + it['quantity']

        for p_id, requested_qty in product_quantities.items():
            prod = prod_by_id.get(p_id)
            if prod:
                stock_val = prod.get('stock')
                if stock_val is not None and str(stock_val).strip() != '':
                    try:
                        available = int(str(stock_val).strip())
                        if available >= 0 and requested_qty > available:
                            raise ValueError(f'Insufficient stock for "{prod.get("name")}". Available: {available}, requested: {requested_qty}.')
                    except ValueError as e:
                        if 'Insufficient stock' in str(e):
                            raise

    return items

def order_data(form, user_products=None):
    if user_products is None:
        try:
            if current_user and current_user.is_authenticated:
                user_products = repo().list_products(current_user.id)
        except Exception:
            user_products = None

    items = parse_order_items(form, user_products)
    calc = calculate(items, form.get('other_cost', '0'))
    return {
        'customer_name': form.get('customer_name', '').strip(),
        'customer_contact': form.get('customer_contact', '').strip(),
        'delivery_address': form.get('delivery_address', '').strip(),
        'delivery_date': form.get('delivery_date', '').strip() or form.get('delivery_request_text', '').strip(),
        'payment_terms': form.get('payment_terms', '').strip(),
        'original_message': form.get('original_message', '').strip(),
        'reply_draft': form.get('reply_draft', '').strip(),
        'status': form.get('status', 'Draft'),
        'items': items,
        'other_cost': str(calc['other_cost']),
        'calculation': {k: (str(v) if v is not None else None) for k, v in calc.items() if k != 'missing_costs'},
        'missing_fields': form.getlist('missing_fields') if hasattr(form, 'getlist') else (form.get('missing_fields') if isinstance(form.get('missing_fields'), list) else []),
    }


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = repo().by_email(request.form.get('email', ''))
        if u and check_password_hash(u['password'], request.form.get('password', '')):
            login_user(User(u))
            return redirect(url_for('dashboard.home'))
        flash('Invalid email or password.', 'error')
    return render_template('auth.html', mode='login')

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        business = request.form.get('business_name', '').strip()
        if '@' not in email or len(password) < 8 or not business:
            flash('Use a business name, valid email, and password of 8+ characters.', 'error')
        elif repo().by_email(email):
            flash('An account already uses that email.', 'error')
        else:
            try:
                u = repo().create_user(email, password, business)
                login_user(User(u))
                return redirect(url_for('dashboard.home'))
            except DuplicateKeyError:
                flash('An account already uses that email.', 'error')
    return render_template('auth.html', mode='register')

@auth.post('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@dashboard.get('/')
@login_required
def home():
    all_orders = repo().list_orders(current_user.id)
    confirmed = [o for o in all_orders if o.get('status') in ('Confirmed', 'Packing', 'Shipped', 'Delivered')]
    revenue = sum((Decimal(str(o.get('calculation', {}).get('subtotal') or '0')) for o in confirmed), Decimal('0'))
    profit = sum((Decimal(str(o.get('calculation', {}).get('estimated_profit') or '0')) for o in confirmed), Decimal('0'))
    return render_template(
        'dashboard.html',
        orders=all_orders[:6],
        stats={
            'total': len(all_orders),
            'awaiting': len([o for o in all_orders if o.get('status') in ('Draft', 'Needs confirmation')]),
            'active': len([o for o in all_orders if o.get('status') in ('Packing', 'Shipped')]),
            'revenue': revenue,
            'profit': profit,
        }
    )

@products.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        try:
            repo().create_product(current_user.id, product_data(request.form))
            flash('Product added.', 'success')
        except ValueError as e:
            flash(str(e), 'error')
        return redirect(url_for('products.index'))
    return render_template('products.html', products=repo().list_products(current_user.id, request.args.get('q', '')))

@products.route('/<id>/edit', methods=['POST'])
@login_required
def edit_product(id):
    try:
        if not repo().update_product(current_user.id, id, product_data(request.form)):
            abort(404)
        flash('Product updated.', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    return redirect(url_for('products.index'))

@products.route('/<id>/delete', methods=['POST'])
@login_required
def delete_product(id):
    if not repo().delete_product(current_user.id, id):
        abort(404)
    flash('Product deleted.', 'success')
    return redirect(url_for('products.index'))

@orders.get('/')
@login_required
def list_orders():
    return render_template('orders.html', orders=repo().list_orders(current_user.id, request.args.get('q', ''), request.args.get('status', '')))

@orders.route('/new', methods=['GET', 'POST'])
@login_required
def new_order():
    user_products = repo().list_products(current_user.id)
    if request.method == 'POST':
        token = request.form.get('submission_token', '').strip()
        if token:
            used = session.get('used_order_tokens', {})
            if token in used:
                existing_order_id = used[token]
                flash('This order has already been saved.', 'info')
                return redirect(url_for('orders.detail', id=existing_order_id))

        try:
            order_dict = order_data(request.form, user_products)
            o = repo().create_order(current_user.id, order_dict)
            if not o or not o.get('_id'):
                raise RuntimeError('Failed to persist order to database.')

            if token:
                used = session.get('used_order_tokens', {})
                used[token] = str(o['_id'])
                session['used_order_tokens'] = used

            flash(f"Order saved as {o.get('status', 'Draft')}.", 'success')
            return redirect(url_for('orders.detail', id=str(o['_id'])))
        except ValueError as e:
            flash(str(e), 'error')
            preserved = preserve_order_from_form(request.form)
            return render_template(
                'order_form.html',
                order=preserved,
                products=user_products,
                extraction=None,
                submission_token=token or uuid.uuid4().hex
            )
        except Exception as e:
            current_app.logger.exception('Failed to save order in repository')
            flash('Database error while saving order. Please try again.', 'error')
            preserved = preserve_order_from_form(request.form)
            return render_template(
                'order_form.html',
                order=preserved,
                products=user_products,
                extraction=None,
                submission_token=token or uuid.uuid4().hex
            )

    token = uuid.uuid4().hex
    return render_template('order_form.html', order={}, products=user_products, extraction=None, submission_token=token)

@orders.post('/extract')
@login_required
def extract():
    # Defensive fallback: if an order submission accidentally posts to /orders/extract
    if 'item_name' in request.form and not request.form.get('is_extract_action'):
        return new_order()

    msg = request.form.get('original_message', '').strip()
    user_products = repo().list_products(current_user.id)
    if not msg:
        flash('Paste a customer message first.', 'error')
        return redirect(url_for('orders.new_order'))

    catalogue_summary = [{'name': p['name'], 'price': p['selling_price']} for p in user_products]
    try:
        out = GemmaService(current_app.config).extract(msg, catalogue_summary)
    except GemmaError as e:
        flash(str(e), 'error')
        out = None

    if out and isinstance(out.get('items'), list):
        for item in out['items']:
            prod_name = item.get('product_name')
            matched = match_catalogue_product(prod_name, user_products)
            if matched:
                item['matched_product_id'] = str(matched.get('_id', ''))
                item['matched_product_name'] = matched.get('name', '')
                cat_price = matched.get('selling_price', '')
                item['catalogue_selling_price'] = cat_price
                item['unit_cost'] = matched.get('unit_cost', '')
                item['packaging_cost'] = matched.get('packaging_cost', '0.00')

                quoted = item.get('quoted_unit_price')
                if quoted and cat_price:
                    try:
                        if Decimal(str(quoted)) != Decimal(str(cat_price)):
                            item['price_needs_verification'] = True
                            item['price_mismatch'] = True
                        else:
                            item['price_needs_verification'] = False
                            item['price_mismatch'] = False
                    except (InvalidOperation, ValueError):
                        item['price_needs_verification'] = True
                elif not quoted and cat_price:
                    item['quoted_unit_price'] = cat_price
                    item['price_needs_verification'] = False
            else:
                item['matched_product_id'] = ''
                item['matched_product_name'] = ''
                item['catalogue_selling_price'] = ''
                item['unit_cost'] = ''
                item['packaging_cost'] = ''
                item['price_needs_verification'] = True

    return render_template(
        'order_form.html',
        order={
            'original_message': msg,
            'delivery_date': out.get('delivery_request_text', '') if out else '',
        },
        products=user_products,
        extraction=out,
        submission_token=uuid.uuid4().hex
    )


@orders.route('/<id>', methods=['GET', 'POST'])
@login_required
def detail(id):
    order = repo().get_order(current_user.id, id)
    if not order:
        abort(404)
    user_products = repo().list_products(current_user.id)
    if request.method == 'POST':
        try:
            status = request.form.get('status', 'Draft')
            valid = {
                'Draft': ['Draft', 'Needs confirmation', 'Cancelled'],
                'Needs confirmation': ['Needs confirmation', 'Confirmed', 'Cancelled'],
                'Confirmed': ['Confirmed', 'Packing', 'Cancelled'],
                'Packing': ['Packing', 'Shipped', 'Cancelled'],
                'Shipped': ['Shipped', 'Delivered'],
                'Delivered': ['Delivered'],
                'Cancelled': ['Cancelled'],
            }
            if status not in valid.get(order.get('status', 'Draft'), []):
                raise ValueError('That status transition is not allowed.')
            repo().update_order(current_user.id, id, order_data(request.form, user_products))
            flash('Order updated.', 'success')
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            current_app.logger.exception('Failed to update order in repository')
            flash('Database error while updating order. Please try again.', 'error')
        return redirect(url_for('orders.detail', id=id))
    return render_template('order_detail.html', order=order, products=user_products)

@orders.get('/<id>/invoice')
@login_required
def invoice(id):
    o = repo().get_order(current_user.id, id)
    if not o:
        abort(404)
    return render_template('invoice.html', order=o)

@orders.post('/<id>/speak')
@login_required
def speak(id):
    """Accept a POST with optional reply_text in the form body.
    - If Accept: application/json (XHR from the template), return JSON {audio_url, download_url}.
    - Otherwise (direct form POST fallback), redirect with a flash message.
    The order must belong to the authenticated user.
    """
    order = repo().get_order(current_user.id, id)
    if not order:
        abort(404)

    # Allow the seller to pass edited text from the textarea without saving first.
    # Fall back to the stored reply_draft.
    reply_text = request.form.get('reply_text', '').strip() or order.get('reply_draft', '').strip()
    is_json_request = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.accept_mimetypes.accept_json
    )

    if not reply_text:
        msg = 'No reply text. Enter a reply draft before generating audio.'
        if is_json_request:
            return jsonify(error=msg), 400
        flash(msg, 'error')
        return redirect(url_for('orders.detail', id=id))

    try:
        service = ElevenLabsService(current_app.config)
        audio_bytes = service.speech(reply_text)
        # Store temporarily in app context keyed by order id so /audio can serve it.
        # In a production multi-worker setup you would use a cache or object store;
        # for Gunicorn single-worker / demo this is safe and avoids writing to disk.
        if 'audio_cache' not in current_app.extensions:
            current_app.extensions['audio_cache'] = {}
        current_app.extensions['audio_cache'][id] = audio_bytes

        audio_url = url_for('orders.audio', id=id)
        download_url = url_for('orders.download_audio', id=id)
        if is_json_request:
            return jsonify(audio_url=audio_url, download_url=download_url)
        # Fallback: stream MP3 directly (non-JS browsers / curl)
        return Response(
            audio_bytes,
            mimetype='audio/mpeg',
            headers={'Content-Disposition': f'attachment; filename=dukaanflow-reply-{id}.mp3'}
        )
    except (RuntimeError, ValueError) as e:
        if is_json_request:
            return jsonify(error=str(e)), 503
        flash(f'Audio error: {e}', 'error')
        return redirect(url_for('orders.detail', id=id))


@orders.get('/<id>/audio')
@login_required
def audio(id):
    """Stream the most-recently generated MP3 for this order (for <audio src=>)."""
    order = repo().get_order(current_user.id, id)
    if not order:
        abort(404)
    cache = current_app.extensions.get('audio_cache', {})
    data = cache.get(id)
    if not data:
        abort(404)
    return Response(
        data,
        mimetype='audio/mpeg',
        headers={'Content-Length': str(len(data)), 'Cache-Control': 'no-store'}
    )


@orders.get('/<id>/audio/download')
@login_required
def download_audio(id):
    """Return the most-recently generated MP3 as a file download attachment."""
    order = repo().get_order(current_user.id, id)
    if not order:
        abort(404)
    cache = current_app.extensions.get('audio_cache', {})
    data = cache.get(id)
    if not data:
        abort(404)
    return Response(
        data,
        mimetype='audio/mpeg',
        headers={
            'Content-Disposition': f'attachment; filename=dukaanflow-reply-{id}.mp3',
            'Content-Length': str(len(data)),
            'Cache-Control': 'no-store',
        }
    )


@integrations.get('/')
@login_required
def settings():
    return render_template(
        'settings.html',
        gemma=GemmaService(current_app.config).configured,
        voice=ElevenLabsService(current_app.config).configured,
        db=repo().status,
        env=current_app.config['ENVIRONMENT']
    )

