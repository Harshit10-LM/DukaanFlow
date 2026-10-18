# DukaanFlow AI — Codebase & Architecture Audit

## 1. Executive Summary

DukaanFlow AI is a Flask and MongoDB Atlas web application built to help small Indian businesses and independent sellers convert unstructured customer conversations (e.g. from WhatsApp, Instagram DMs) into reviewable, fulfilment-ready orders with deterministic financial calculations.

This audit documents the findings from inspecting the entire repository, verifying live database and service connections, reproducing reported bugs, and establishing the technical path toward production readiness on GitHub and Render.

---

## 2. Actual Technology Stack

- **Backend Framework**: Python 3.13, Flask 3.1.2
- **Authentication & Sessions**: Flask-Login 0.6.3, Werkzeug password hashing (scrypt)
- **Security & Forms**: Flask-WTF 1.2.2 (CSRF protection, secure cookie flags)
- **Database**: MongoDB Atlas via PyMongo 4.16.0 (with in-memory demo mode fallback when `MONGODB_URI` is unset)
- **AI Extraction**: Open-weight Gemma model (`gemma-4-26b-a4b-it`) accessed via the official `google-genai` SDK (v1.64.0)
- **Audio Synthesis**: ElevenLabs Python SDK (`elevenlabs` v2.73.0) for seller-approved Speak & Share replies
- **Financial Arithmetic**: Python standard library `decimal.Decimal` with integer/paise rounding (`ROUND_HALF_UP`)
- **Server & Deployment**: Gunicorn 23.0.0, Render Web Service (`render.yaml`), WSGI entry point (`wsgi.py`)
- **Testing**: pytest 8.4.2

---

## 3. Project Architecture & Current Application Flow

### Application Structure
```
DukaanFlow AI/
├── app/
│   ├── __init__.py           # Flask app factory, LoginManager, CSRFProtect, repo init, health route
│   ├── config.py             # Config loading from environment variables via python-dotenv
│   ├── models.py             # User model wrapping MongoDB user document for Flask-Login
│   ├── repository.py         # PyMongo repository with multi-tenant data isolation & demo fallback
│   ├── views.py              # Blueprints: auth, dashboard, products, orders, integrations
│   ├── services/
│   │   ├── gemma_service.py      # Gemma extraction boundary, schema enforcement, error handling
│   │   ├── profit_calculator.py  # Deterministic Decimal financial math (subtotal, costs, profit)
│   │   └── elevenlabs_service.py # Text-to-speech generation for approved replies
│   ├── static/
│   │   └── style.css         # Responsive styling, color tokens, typography
│   └── templates/
│       ├── base.html         # Main shell layout with sidebar and status badges
│       ├── auth.html         # Login and registration forms
│       ├── dashboard.html    # Order counts, status summaries, revenue & profit metrics
│       ├── products.html     # Catalogue management (add, delete, search)
│       ├── orders.html       # Order listings with status filtering
│       ├── order_form.html   # Message paste, Gemma extraction, order review form
│       ├── order_detail.html # Single order view, status transitions, reply audio generation
│       ├── invoice.html      # Printable order summary and invoice
│       └── settings.html     # Integration status and liveness checks
├── docs/                     # Architecture, deployment, setup guides
├── tests/                    # Unit and integration tests (test_app, test_gemma_service, test_profit_calculator)
├── tools/                    # One-shot diagnostics (gemma_diagnostic.py)
├── render.yaml               # Infrastructure-as-code for Render deployment
├── requirements.txt          # Python runtime dependencies
└── wsgi.py                   # WSGI entry point (`app = create_app()`)
```

### Flow of Execution
1. **User Authentication**: Sellers register with business name, email, and password (min 8 chars, hashed with scrypt).
2. **Product Catalogue**: Sellers create products with name, SKU, selling price, unit cost, packaging cost, and stock.
3. **Order Capture**:
   - The seller pastes a customer conversation into `orders.new_order`.
   - `orders.extract` sends the text + catalogue reference to `GemmaService`.
   - Gemma extracts structured JSON conforming to `ORDER_SCHEMA`.
4. **Order Review & Persistence**:
   - The seller reviews the parsed fields, adjusts quantities or variants, confirms pricing, and saves the order.
   - Financials are deterministically calculated using `profit_calculator.py`.
   - Order is saved to MongoDB in `orders` collection under `user_id`.
5. **Fulfilment & Status Lifecycle**:
   - Order transitions through guarded states: `Draft` → `Needs confirmation` → `Confirmed` → `Packing` → `Shipped` → `Delivered` (or `Cancelled`).
6. **Customer Communication & Audio**:
   - The seller edits/approves the customer reply draft.
   - An approved reply can be synthesized into an MP3 via ElevenLabs and downloaded.

---

## 4. Database Schema & Persistence Behaviour

### Users (`db.users`)
- `_id`: ObjectId
- `email`: string (unique indexed, lowercase)
- `password`: string (werkzeug scrypt hash)
- `business_name`: string
- `created_at`: UTC datetime

### Products (`db.products`)
- `_id`: ObjectId
- `user_id`: string (indexed with `name`)
- `name`: string
- `sku`: string (optional)
- `description`: string (optional)
- `selling_price`: string (Decimal representation, e.g. "650.00")
- `unit_cost`: string (Decimal representation, e.g. "350.00")
- `packaging_cost`: string (Decimal representation, e.g. "20.00")
- `stock`: string / integer
- `created_at`, `updated_at`: UTC datetime

### Orders (`db.orders`)
- `_id`: ObjectId
- `user_id`: string (indexed with `created_at`)
- `customer_name`: string
- `customer_contact`: string
- `delivery_address`: string
- `payment_terms`: string
- `original_message`: string
- `reply_draft`: string
- `status`: string (`Draft`, `Needs confirmation`, `Confirmed`, `Packing`, `Shipped`, `Delivered`, `Cancelled`)
- `items`: list of item objects:
  - `name`: string
  - `variant`: string
  - `quantity`: integer
  - `selling_price`: string (Decimal)
  - `unit_cost`: string (Decimal)
  - `packaging_cost`: string (Decimal)
  - `product_id`: string (optional reference to catalogue product)
  - `quoted_price`: string (optional customer stated price)
  - `price_needs_verification`: boolean
- `other_cost`: string (Decimal)
- `calculation`:
  - `subtotal`: string (Decimal)
  - `product_cost`: string (Decimal)
  - `packaging_cost`: string (Decimal)
  - `other_cost`: string (Decimal)
  - `estimated_profit`: string (Decimal)
  - `margin`: string (percentage)
  - `missing_costs`: list of strings
- `missing_fields`: list of strings
- `created_at`, `updated_at`: UTC datetime

---

## 5. Integrations Status

### Gemma Integration
- **Model**: `gemma-4-26b-a4b-it` via `google-genai` SDK.
- **Verification**: Verified using `tools/gemma_diagnostic.py` and direct execution. The API key is valid and responds with structured output.
- **Identified Issue**:
  - The extraction prompt currently allows Gemma to aggregate multi-variant requests into a single item (e.g. "two navy kurtis, one medium and one large" extracted as 1 line item with quantity 2, variant "medium", losing the "large" variant).
  - The system prompt needs explicit instructions that distinct variants (sizes, colors) MUST each become separate line items with their respective quantities.

### ElevenLabs Integration
- **Model**: Configured with `ELEVENLABS_MODEL_ID` (default `eleven_v3` or `eleven_multilingual_v2`).
- **Verification**: Current API key test against ElevenLabs returned HTTP 401 Unauthorized (invalid API key).
- **Behavior**: The application correctly guards ElevenLabs behind `configured` check (`ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID`). When calls fail or credentials are missing/invalid, it returns HTTP 503 with a user-friendly error and does not break the core order flow.
- **Action**: Provide comprehensive mock tests, harden error handling, and document exact steps for live testing when valid credentials are provided.

---

## 6. Confirmed Bugs & Architectural Gaps

1. **Single-Item Data Model Restriction across the Entire Application**:
   - `order_data(form)` in `views.py` only parses scalar form values: `form.get('item_name')`, `form.get('variant')`, `form.get('quantity')`, `form.get('selling_price')`, `form.get('unit_cost')`, `form.get('packaging_cost')`. It ignores any second or subsequent items.
   - `order_form.html` only renders inputs for `extracted_items[0]`.
   - `order_detail.html` only displays and provides edit fields for `order['items'][0]`.
   - If an order has multiple items, viewing or saving it overwrites the order with only the first item.
2. **Missing Catalogue Cost Auto-Population**:
   - In `views.py:extract`, only `{'name': p['name'], 'price': p['selling_price']}` was passed to Gemma.
   - After extraction, no catalogue lookup or matching occurs. The unit cost and packaging cost remain blank in `order_form.html`.
   - Catalogue products in MongoDB Atlas (`Navy Kurti` at ₹650 selling, ₹350 unit cost, ₹20 packaging) never populate into the extracted order lines.
3. **Gemma Variant Collapsing**:
   - In `gemma_service.py`, `SYSTEM_INSTRUCTION` does not mandate splitting different sizes/variants into distinct items. As a result, "two navy kurtis, one medium and one large" was parsed as `quantity: 2, variant: 'medium'`.
4. **Template Bugs & Dangerous Assumptions**:
   - In `invoice.html`: `<td>₹{{order.calculation.subtotal}}</td>` is rendered inside `{% for i in order['items'] %}`, showing the grand subtotal for every line item instead of the line's own total (`quantity * selling_price`).
   - In `orders.html`: `<td>{{o['items'][0].name}}</td>` fails if `items` is empty, and hides all items except the first.
   - In `order_detail.html`: `{% set i=order['items'][0] %}` will raise `IndexError` if an order has empty items.
5. **No Dynamic Line Item Addition/Removal in UI**:
   - Neither `order_form.html` nor `order_detail.html` allows sellers to add another line item, delete a line, or select from catalogue items dynamically.
6. **Price Verification & Mismatch Highlighting**:
   - When customer quoted price differs from catalogue price, the UI does not clearly show the comparison or require explicit approval.

---

## 7. Security and Deployment Review

- **CSRF Protection**: Enabled via `Flask-WTF` on all POST routes.
- **Multi-Tenant Isolation**: Repository methods enforce `user_id=current_user.id` on all product and order operations. Cross-user access is safely rejected with `None` / 404.
- **ObjectID Validation**: `oid()` helper converts strings safely, preventing BSON invalid format exceptions from crashing endpoints.
- **Production Secret Enforcements**: In `create_app()`, production mode enforces `SECRET_KEY` and `MONGODB_URI`.
- **Render Deployment**: `render.yaml` specifies Python runtime, `pip install -r requirements.txt`, `gunicorn wsgi:app`, `/health` health check.

---

## 8. Prioritized Implementation Plan

1. **Order Data Model & Multi-Line Parsing**:
   - Update `views.py` `order_data()` to handle indexed line items (`items[0][name]`, `items[1][name]` or list parameters) supporting arbitrary numbers of items.
   - Ensure backwards compatibility for legacy single-item orders (`item_name` / `variant` fallback).
2. **Catalogue Auto-Matching & Cost Lookup**:
   - In `orders.extract`, match extracted items against the seller's catalogue products.
   - Auto-populate `unit_cost`, `packaging_cost`, and catalogue reference.
   - Flag price verification if quoted price differs from catalogue price.
3. **Gemma Multi-Variant Extraction Prompt**:
   - Enhance system instruction in `gemma_service.py` to strictly split distinct variants into separate items with individual quantities.
4. **Templates & Interactive Line Items**:
   - Overhaul `order_form.html` and `order_detail.html` to render all line items with Add/Remove item buttons and product selector.
   - Fix `invoice.html` line subtotal calculation.
   - Fix `orders.html` item summary display.
   - Ensure safe dictionary and list access across all templates.
5. **Profit Calculator Verification**:
   - Verify line-by-line calculations: line subtotal, line cost, line packaging, order totals, profit, and margin.
6. **ElevenLabs Robustness**:
   - Harden error handling and status reporting.
7. **Automated Test Suite Expansion**:
   - Add comprehensive tests covering multi-line orders, variant splitting, catalogue cost populating, pricing mismatches, and security boundaries.

---

## 9. Implementation Results & Resolution Verification

All prioritized fixes have been fully implemented, tested, and verified:

| Component / Bug | Prior State | Implemented Resolution | Verified Status |
|---|---|---|---|
| **Multi-Variant Extraction** | Gemma combined "one medium and one large" into qty 2, variant "medium" | Added `CRITICAL MULTI-ITEM AND VARIANT RULE` in `SYSTEM_INSTRUCTION` in `gemma_service.py` | **Verified**: Live Gemma API extracted 2 separate items (Medium, Large) with qty 1 each. |
| **Multi-Line Data Model** | `order_data()` only parsed single scalar input values | Implemented `parse_order_items()` in `views.py` supporting arbitrary line items via lists and indexed fields | **Verified**: Preserves all items throughout extraction, review, save, and MongoDB persistence. |
| **Catalogue Cost Auto-Population** | Extracted items left unit & packaging costs completely blank | Implemented `match_catalogue_product()` in `views.py` matching seller products and populating costs | **Verified**: Extracted Navy Kurtis automatically populated unit cost ₹350 and packaging ₹20. |
| **Price Verification** | Quoted prices were not checked against catalogue prices | Added price mismatch comparison logic (`price_mismatch`, `price_needs_verification`) with UI badges | **Verified**: Highlights differences when quoted != catalogue selling price. |
| **Order Detail Edit Bug** | `order_detail.html` only showed item[0] and overwrote multiple lines on save | Rewrote `order_detail.html` with full multi-line table and editable line-item cards | **Verified**: Multi-line edits save and recalculate correctly. |
| **Invoice Subtotal Bug** | `invoice.html` rendered the grand subtotal on every line item | Fixed line total to `(quantity * selling_price)` with an itemized breakdown | **Verified**: Line subtotals render accurately in invoice and print preview. |
| **Orders List IndexError** | `orders.html` accessed `o['items'][0].name` without empty checks | Updated to safe `o.get('items', [])` with multi-item summary pill | **Verified**: Safe against 0, 1, or N items. |
| **Financial Calculations** | Margin had unrounded precision and no line subtotals | Attached `line_subtotal` and quantized margin to 2 decimal places using `ROUND_HALF_UP` | **Verified**: ₹1300 revenue, ₹700 cost, ₹40 pkg -> ₹560 profit, 43.08% margin. |
| **ElevenLabs Resilience** | Unconfigured/failed voice threw raw JSON 503 breaking page | Upgraded `ElevenLabsService` with `client_factory` and safe flash error redirects | **Verified**: Handles 401, 404, 429 safely without crashing the order workflow. |
| **Automated Testing** | 18 passing tests with single-item coverage | Expanded to 35 comprehensive tests covering all edge cases, mocks, and security boundaries | **Verified**: 35 passed in 1.54s. |

