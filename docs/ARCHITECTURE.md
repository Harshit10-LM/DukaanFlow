# DukaanFlow AI — System Architecture

## 1. Overview & Architectural Principles

DukaanFlow AI bridges informal conversational commerce (WhatsApp, Instagram DMs, chat) with structured, reliable order management and accounting for small merchants.

### Core Architectural Decisions:
1. **AI as an Assistant, Not an Authority**: The AI model extracts raw facts and suggests structured line items. It is never allowed to calculate financial totals, confirm orders, or make inventory decisions.
2. **Deterministic Financial Math**: All currency arithmetic is strictly computed server-side in Python using `decimal.Decimal` with explicit `ROUND_HALF_UP` paise rounding. No floating-point or generative AI math is permitted.
3. **Multi-Variant Line Items**: Customers often request multiple sizes or colors in a single sentence (e.g. "one medium and one large"). The data model and extraction pipeline preserve distinct variants as separate fulfilment lines with individual quantities.
4. **Catalogue-Grounded Costings**: Extracted item names are matched against the seller's verified product catalogue to automatically populate unit manufacturing and packaging costs. Quoted prices from messages are checked against catalogue prices, flagging mismatches for seller review.
5. **Strict Multi-Tenant Isolation**: All database operations scope records by authenticated `user_id`. One merchant cannot view, edit, or delete another merchant's products or orders.

---

## 2. Component Diagram

```
+-------------------------------------------------------------------------+
|                              Web Browser                                |
|  - Dashboard (Metrics)  - Products Catalogue  - Multi-Line Order Capture|
|  - Live Calculation JS  - Order Review/Edit   - Printable Invoice HTML  |
+-------------------------------------------------------------------------+
                                    |  HTTP / CSRF Protected
                                    v
+-------------------------------------------------------------------------+
|                        Flask Application (WSGI)                         |
|  - auth Blueprint (login, register, logout with Werkzeug scrypt hashing)|
|  - dashboard Blueprint (revenue, profit, order status summaries)       |
|  - products Blueprint (CRUD catalogue with monetary validation)         |
|  - orders Blueprint (extract, review, save, detail, invoice, speak)     |
|  - integrations Blueprint (settings & liveness check)                  |
+-------------------------------------------------------------------------+
        |                    |                        |              |
        v                    v                        v              v
+---------------+  +-------------------+  +---------------+  +--------------+
| GemmaService  |  | ProfitCalculator  |  | ElevenLabsSvc |  |  Repository  |
| - google-genai|  | - Decimal math    |  | - elevenlabs  |  | - PyMongo /  |
| - JSON schema |  | - Line subtotals  |  | - Voice TTS   |  |   Demo mode  |
| - Multi-item  |  | - Cost totals     |  | - Stream MP3  |  | - Users      |
|   prompting   |  | - Profit & margin |  |   bytes       |  | - Products   |
+---------------+  +-------------------+  +---------------+  | - Orders     |
                                                             +--------------+
                                                                     |
                                                                     v
                                                             +--------------+
                                                             |   MongoDB    |
                                                             |    Atlas     |
                                                             +--------------+
```

---

## 3. Data Flow: Multi-Variant Order Processing

1. **Input**: Merchant pastes raw conversation into Order Capture.
2. **Extraction (`GemmaService`)**:
   - Customer message is treated strictly as untrusted data within a bounded prompt.
   - Gemma is constrained by system instructions to split multiple variants/sizes into individual items.
   - Strict JSON response conforming to `ORDER_SCHEMA` is returned.
3. **Catalogue Resolution (`match_catalogue_product`)**:
   - Each extracted item is matched against the seller's active product database.
   - Verified catalogue selling price, unit cost, and packaging cost are populated.
   - If customer-quoted price differs from catalogue price, `price_mismatch` and `price_needs_verification` are set to `True`.
4. **Interactive Review (`order_form.html`)**:
   - The seller reviews each line item separately, with the ability to add, edit, or remove lines.
   - Frontend JavaScript provides real-time totals breakdown.
5. **Validation & Persistence (`views.py:order_data` & `repository.py`)**:
   - Server validates all quantities and monetary values.
   - `profit_calculator.py` computes authoritative financials.
   - Order document with full `items` array is persisted in MongoDB Atlas under merchant's `user_id`.
6. **Fulfilment & Voice Audio**:
   - Merchant advances order status through guarded lifecycle states.
   - Approved customer reply can be converted into high-fidelity voice audio via ElevenLabs for voice note sharing.
