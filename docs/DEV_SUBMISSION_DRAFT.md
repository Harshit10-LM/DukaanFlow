# DukaanFlow AI — Conversational Order Management & Financial Clarity for Small Businesses

*Submission for Hacktoberfest 2026 / DEV Challenge*

Tags: `#devchallenge` `#hf26challenge` `#ai` `#python`

---

## 1. What I Built

**DukaanFlow AI** is an AI-powered order management and financial clarity web application designed for home entrepreneurs, boutique designers, and small business merchants in India who receive the majority of their customer orders through informal messaging channels like **WhatsApp** and **Instagram DMs**.

Instead of manually copying customer messages into messy spreadsheets—or falling prey to generic chatbots that hallucinate numbers—merchants use DukaanFlow AI to:
1. Paste unstructured customer chats.
2. Have open-weight **Gemma** extract customer facts, splitting multi-variant requests (e.g. "two navy kurtis, one medium and one large") into individual fulfilment line items.
3. Automatically match items against the merchant's catalogue, auto-populating verified unit manufacturing and packaging costs.
4. Highlight price discrepancies when a customer's quoted amount doesn't match catalogue pricing.
5. Deterministically calculate subtotal, product costs, packaging costs, and estimated profit/margin using Python's `decimal.Decimal`.
6. Generate downloadable **ElevenLabs** voice audio for approved reply drafts so sellers can send polished audio notes back to customers on WhatsApp.
7. Print itemized invoices and manage orders through guarded fulfilment stages.

---

## 2. Demo

- **Deployed Application**: [Insert Render URL here after deployment]
- **Repository**: [Insert GitHub Repository URL]
- **Sample Test Flow**:
  - Customer Message: *"Hi, I need two navy kurtis, one medium and one large. The price is ₹650 each, right? Can you deliver by Friday? I'll pay half now and the rest on delivery."*
  - Extracted Lines: Line 1 (Medium, Qty 1, ₹650), Line 2 (Large, Qty 1, ₹650).
  - Catalogue Matching: Both matched to "Navy Kurti", auto-populating unit cost (₹350) and packaging cost (₹20).
  - Financials: Subtotal ₹1,300, Product Cost ₹700, Packaging Cost ₹40, Estimated Profit ₹560 (43.08% margin).

---

## 3. How I Built It

- **Backend**: Python 3.13, Flask 3, Werkzeug, Flask-Login, Flask-WTF.
- **AI Extraction**: Open-weight **Gemma** (`gemma-4-26b-a4b-it`) via the `google-genai` SDK with strict JSON schema enforcement and multi-variant system prompting.
- **Database**: **MongoDB Atlas** with PyMongo, featuring strict per-user multi-tenant data isolation and compound indexing.
- **Voice Synthesis**: **ElevenLabs Python SDK** with text-to-speech conversion for seller-approved replies.
- **Financial Arithmetic**: `decimal.Decimal` with integer paise rounding (`ROUND_HALF_UP`).
- **Deployment**: **Render** Web Service managed via `render.yaml` and Gunicorn WSGI.

---

## 4. Why Does Open Innovation Matter?

Small business workflows shouldn't be locked into proprietary, opaque closed-model APIs. DukaanFlow AI is built on open-weight **Gemma**, ensuring that merchants and developers can inspect, fine-tune, self-host, or adapt their models as open-weight AI advances. Furthermore, the application treats generative AI as an extraction assistant rather than a financial calculator, keeping accounting deterministic, transparent, and auditable.

---

## 5. Prize Tracks Entered

- **Best Use of Render**: Infrastructure-as-code deployment via `render.yaml`, seamless Gunicorn production serving, and automated `/health` liveness checks.
- **Best Use of Gemma**: Zero-shot structured data extraction from noisy, multi-lingual conversational messages into strict multi-line JSON schemas.
- **Best Use of MongoDB Atlas**: Fully managed document database with per-tenant scoping, compound indexes, and reliable persistence.
- **Best Use of ElevenLabs**: High-fidelity text-to-speech audio synthesis for personalized voice notes.
