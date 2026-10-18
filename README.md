# DukaanFlow AI

**Turn messy conversational customer messages into fulfilment-ready orders with clear financial intelligence.**

DukaanFlow AI is an AI-powered order management application for home businesses, boutique fashion labels, and independent merchants who receive customer orders through informal messaging channels such as **WhatsApp**, **Instagram DMs**, and chat apps.

Instead of manual spreadsheet entry or unreliable generative math, DukaanFlow AI pairs open-weight **Gemma** extraction with seller-governed, deterministic **Decimal** accounting, **MongoDB Atlas** persistence, and **ElevenLabs** voice generation.

---

## The Business Problem

Millions of independent Indian merchants sell through direct messaging. A typical customer order arrives like this:

> *"Hi, I need two navy kurtis, one medium and one large. The price is ₹650 each, right? Can you deliver by Friday? I'll pay half now and the rest on delivery."*

Traditional solutions fail these sellers:
- **Generic Spreadsheets**: Require manual copy-pasting, error-prone manual calculations, and separate invoicing.
- **Autonomous AI Chatbots**: Hallucinate discounts, confirm orders without checking stock, and guess financial totals.
- **Lost Variants**: Naive parsing collapses "one medium and one large" into a single item with quantity 2, leading to fulfilment errors.
- **Hidden Margins**: Merchants rarely calculate unit manufacturing, packaging, and shipping costs on each sale, causing unprofitable sales.

DukaanFlow AI solves this by keeping the merchant in control: AI extracts the facts; catalogue data populates verified costs; deterministic arithmetic calculates real profit; and merchants review every detail before confirming.

---

## Core Features

- **Multi-Line & Multi-Variant Extraction**: Extracts distinct variants (e.g. Medium and Large) as separate fulfilment line items with individual quantities.
- **Catalogue Matching & Cost Auto-Population**: Matches extracted items to catalogue products, automatically pulling verified selling prices, unit costs, and packaging costs.
- **Price Discrepancy Highlighting**: Compares customer-quoted prices against catalogue prices and flags mismatches for seller verification.
- **Deterministic Profit & Margin Arithmetic**: Uses Python's `decimal.Decimal` to calculate exact revenue, costs, estimated profit, and margin percentages. Unknown costs never silently become zero.
- **Order Lifecycle Management**: Guarded order state transitions: `Draft` → `Needs confirmation` → `Confirmed` → `Packing` → `Shipped` → `Delivered` (or `Cancelled`).
- **Interactive Review Interface**: Merchants can add, edit, or remove line items dynamically with live-updating financial summaries.
- **Printable Invoices & Packing Slips**: Itemized printable summary with per-line totals and delivery instructions.
- **ElevenLabs "Speak & Share"**: Synthesizes approved customer replies into audio voice notes for sending on WhatsApp.
- **Secure Multi-Tenant Architecture**: Strict per-user data isolation across users, products, and orders.

---

## Technology Stack & Architecture

- **Backend**: Python 3.13, Flask 3.1, Werkzeug
- **Authentication**: Flask-Login with scrypt password hashing
- **Security & Forms**: Flask-WTF with CSRF protection, HTTP-only secure cookies
- **Database**: MongoDB Atlas via PyMongo (with in-memory demo fallback for local testing without credentials)
- **AI Extraction**: Open-weight **Gemma** (`gemma-4-26b-a4b-it`) via Google's `google-genai` SDK
- **Audio Synthesis**: ElevenLabs Python SDK (`elevenlabs`) for high-fidelity speech generation
- **Production Server**: Gunicorn WSGI on Render (`render.yaml`)

For in-depth architectural diagrams and data flows, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Why Open-Weight AI Matters

DukaanFlow AI purposefully relies on open-weight **Gemma** models. 

1. **Model Independence**: Small merchants and independent developers are not locked into proprietary black-box APIs.
2. **Transparent Boundaries**: Gemma is deployed strictly behind a server-side extraction boundary. It is given untrusted customer text and instructed to output structured facts conforming to a strict JSON schema.
3. **Auditability**: Generative AI never computes financial arithmetic. The model proposes order lines; deterministic code calculates profits.

---

## Multi-Line Item & Price Verification Flow

When a message is received:
1. **Gemma Extraction**: Gemma splits multi-variant requests into discrete objects in an `items` array.
2. **Catalogue Lookup**: The server matches product names against the seller's active catalogue.
3. **Cost Population**: If matched, `unit_cost`, `packaging_cost`, and `catalogue_selling_price` are populated automatically.
4. **Price Verification**:
   - Customer-quoted price == Catalogue price: verified.
   - Customer-quoted price != Catalogue price: flagged with a warning requiring merchant approval.
5. **Deterministic Math**:
   $$\text{Subtotal} = \sum (\text{Quantity} \times \text{Selling Price})$$
   $$\text{Product Cost} = \sum (\text{Quantity} \times \text{Unit Cost})$$
   $$\text{Packaging Cost} = \sum (\text{Quantity} \times \text{Packaging Cost})$$
   $$\text{Estimated Profit} = \text{Subtotal} - \text{Product Cost} - \text{Packaging Cost} - \text{Other Costs}$$
   $$\text{Margin} = \frac{\text{Estimated Profit}}{\text{Subtotal}} \times 100$$

---

## Local Setup

### 1. Clone & Setup Virtual Environment
```bash
git clone <repo-url>
cd "DukaanFlow AI"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
```
Edit `.env` with your API keys:
```ini
SECRET_KEY=replace-with-a-random-secret-key
FLASK_ENV=development
MONGODB_URI=mongodb+srv://<username>:<password>@cluster.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=dukaanflow
GEMMA_API_KEY=your-google-ai-studio-api-key
GEMMA_MODEL=gemma-4-26b-a4b-it
ELEVENLABS_API_KEY=your-elevenlabs-api-key
# Get your Voice ID from https://elevenlabs.io/app/voice-lab
# Pre-made voices work on all plans (e.g. Rachel = 21m00Tcm4TlvDq8ikWAM).
ELEVENLABS_VOICE_ID=your-voice-id
# Recommended: eleven_multilingual_v2 (29 languages incl. English+Hindi, 10k char limit)
# Alternative: eleven_v3 (70+ languages, 5k char limit, more expressive)
ELEVENLABS_MODEL_ID=eleven_multilingual_v2
```

> **Demo Mode**: If `MONGODB_URI` is left blank, the app runs in **demo mode**, storing data in memory with pre-seeded demo accounts (`demo@dukaanflow.test` / `DemoPass123`).

### 3. Verify Gemma Connection
```bash
python tools/gemma_diagnostic.py
```

### 4. Run the Application
```bash
flask --app wsgi run --port 5000 --debug
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

---

## Automated Testing

Run the test suite using pytest:
```bash
python -m pytest -v
```
The test suite includes **46 tests** covering:
- Multi-line item and multi-variant orders.
- Catalogue auto-matching and price mismatch flagging.
- Financial arithmetic, zero/negative validations, and decimal rounding.
- Mocked Gemma extraction, rate limiting, and network timeout handling.
- Mocked ElevenLabs voice generation: successful audio, missing credentials, voice not found (404), auth failure (401/403), quota exceeded (429), unprocessable (422), cross-user isolation, JSON response headers, audio streaming endpoint, MP3 download attachment.
- Cross-user data isolation and guarded status transitions.
- Backward compatibility with legacy single-item order schemas.

---

## Production Deployment to Render

DukaanFlow AI includes a complete `render.yaml` configuration.

1. Connect your repository to Render as a **Blueprint**.
2. Supply your `MONGODB_URI`, `GEMMA_API_KEY`, and optional ElevenLabs keys in the Render dashboard.
3. Render automatically executes:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn wsgi:app`
   - Liveness Check: `/health`

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full deployment instructions.

---

## Privacy, Security & Known Limitations

- **No Direct WhatsApp Scraping**: Customer messages are pasted manually by the merchant. DukaanFlow AI never connects directly to private chat accounts.
- **Provider Boundary**: Messages are transmitted to Google AI Studio only when the seller explicitly clicks "Extract order with Gemma". Audio is generated only when the seller clicks "Generate voice note".
- **Audio Security**: The ElevenLabs API key is never exposed to the browser. Audio bytes are returned via a server-side `/orders/<id>/audio` endpoint gated by Flask-Login session authentication and per-user order ownership checks.
- **Financial Scoping**: Profit calculations represent operating estimates before business taxes, merchant payment gateway fees, and overheads unless entered under "Other costs".
- **ElevenLabs Dependency**: Voice synthesis is optional. If credentials are not configured or the provider experiences downtime, core order management continues without interruption. The "Generate voice note" button returns a clear error; the rest of the page remains fully functional.

---

## License

MIT License. See [LICENSE](LICENSE).
