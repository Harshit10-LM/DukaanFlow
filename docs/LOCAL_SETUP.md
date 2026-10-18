# Local Development & Setup Guide

This guide details how to configure and run **DukaanFlow AI** locally on macOS, Linux, or Windows (WSL2).

---

## 1. Environment Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd "DukaanFlow AI"

# 2. Create and activate a Python virtual environment (Python 3.11+ recommended)
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## 2. Environment Configuration

```bash
cp .env.example .env
```

Edit `.env` with your settings:
```ini
SECRET_KEY=dev-secret-key-replace-in-production
FLASK_ENV=development
MONGODB_URI=mongodb+srv://<user>:<password>@cluster.example.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=dukaanflow
GEMMA_API_KEY=your-google-ai-studio-api-key
GEMMA_MODEL=gemma-4-26b-a4b-it
ELEVENLABS_API_KEY=your-elevenlabs-api-key
ELEVENLABS_VOICE_ID=your-voice-id
ELEVENLABS_MODEL_ID=eleven_multilingual_v2
```

> **Note on Demo Mode**: If `MONGODB_URI` is omitted or empty, the application starts in **demo fallback mode**, which runs completely in memory with seeded mock products and users (`demo@dukaanflow.test` / `DemoPass123`). In demo mode, all data resets when the server restarts.

---

## 3. Running the Diagnostic Tool

Test your Gemma credentials and model availability before starting:
```bash
python tools/gemma_diagnostic.py
```
Output: `Gemma diagnostic: minimal request succeeded for configured Gemma model.`

---

## 4. Running the Application Locally

```bash
# Using Flask development server
flask --app wsgi run --port 5000 --debug

# Or using Gunicorn (production simulation)
gunicorn wsgi:app --bind 127.0.0.1:5000
```

Open your browser at `http://127.0.0.1:5000`.

---

## 5. Running Automated Tests

```bash
# Run full test suite
python -m pytest -v

# Run with quiet output
python -m pytest -q
```
All automated tests use deterministic in-memory fixtures and mocks, requiring no external network connectivity or paid API credits.
