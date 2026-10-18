# Render & Production Deployment Guide

This guide outlines how to deploy **DukaanFlow AI** to Render using MongoDB Atlas and the official open-weight Gemma and ElevenLabs integrations.

---

## 1. Prerequisites

1. **MongoDB Atlas Account**:
   - Create a free or dedicated cluster on MongoDB Atlas.
   - In **Database Access**, create a database user (readWrite role on `dukaanflow`).
   - In **Network Access**, add IP `0.0.0.0/0` (Allow Access from Anywhere) to permit outbound connections from Render's dynamic application IPs.
   - Copy the connection string format: `mongodb+srv://<username>:<password>@cluster.example.mongodb.net/?retryWrites=true&w=majority`.

2. **Google AI Studio API Key**:
   - Obtain an API key from Google AI Studio.
   - The application accesses the open-weight `gemma-4-26b-a4b-it` model via Google's `google-genai` SDK.

3. **ElevenLabs API Key & Voice ID (Optional)**:
   - For seller-approved voice replies, obtain an API key from ElevenLabs.
   - Choose a voice from VoiceLab (e.g. Rachel, Adam, or custom) and copy the Voice ID.

---

## 2. Deploying to Render via `render.yaml` (Recommended)

1. Push your repository to GitHub (ensure `.env` is never committed).
2. Log in to [Render Dashboard](https://dashboard.render.com).
3. Click **New +** → **Blueprint**.
4. Connect your GitHub repository. Render will detect `render.yaml`.
5. Enter the non-synced environment variables in the prompt:
   - `MONGODB_URI`: Your MongoDB Atlas connection URI.
   - `GEMMA_API_KEY`: Your Google AI Studio API key.
   - `ELEVENLABS_API_KEY`: (Optional) Your ElevenLabs API key.
   - `ELEVENLABS_VOICE_ID`: (Optional) Your ElevenLabs Voice ID.
6. Click **Apply**. Render will automatically build the service and start Gunicorn.

---

## 3. Manual Web Service Deployment on Render

If not using Blueprints:
- **Service Type**: Web Service
- **Runtime**: Python 3
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn wsgi:app`
- **Health Check Path**: `/health`

### Environment Variables to Configure in Render:
| Variable | Value / Description | Required? |
|---|---|---|
| `FLASK_ENV` | `production` | Yes |
| `SECRET_KEY` | Generate a 64-char random hex key (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`) | Yes |
| `MONGODB_URI` | `mongodb+srv://...` | Yes |
| `MONGODB_DB` | `dukaanflow` | Yes |
| `GEMMA_API_KEY` | Your Google AI Studio API key | Yes |
| `GEMMA_MODEL` | `gemma-4-26b-a4b-it` | Yes |
| `ELEVENLABS_API_KEY` | Your ElevenLabs API key | Optional |
| `ELEVENLABS_VOICE_ID` | Your ElevenLabs Voice ID | Optional |
| `ELEVENLABS_MODEL_ID` | `eleven_multilingual_v2` | Optional |

---

## 4. Post-Deployment Verification

1. **Liveness & Database Check**:
   - Visit `https://your-app.onrender.com/health`.
   - Expected response: `{"status": "ok", "database": "connected"}`.
2. **Account Creation**:
   - Register a seller account with email, business name, and password.
3. **Catalogue Setup**:
   - Navigate to `/products` and add your products with verified selling prices and unit costs.
4. **Order Capture Flow**:
   - Navigate to `/orders/new`, paste a multi-item customer order, and verify that Gemma extracts separate variants and links catalogue costs.
5. **Printable Invoice**:
   - Open `/orders/<order_id>/invoice` to confirm itemized invoice printing.
6. **Voice Synthesis (Speak & Share)**:
   - Test speech generation for an approved reply draft.
