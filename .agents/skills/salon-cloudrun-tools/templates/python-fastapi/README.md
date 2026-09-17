# Python FastAPI Efficiency Tool Template

A lightweight, production-ready template for building AI-powered efficiency tools deployed to Google Cloud Run and integrated into the Kimiiro Salon platform.

---

## Features

- **FastAPI Framework**: High performance async request handling.
- **Pre-configured CSP Headers**: Automatically enables iframe embedding from `https://kimiiro-salon.web.app` and localhost.
- **Kimidori Themed UI**: Matches the salon's visual standards.
- **PostMessage Integration**: Dispatches `SAVE_DRAFT` events directly to the salon host.
- **Google Gemini API**: Ready-to-use content generation endpoint.
- **Cloud Run Optimized Dockerfile**: Minimal image size, non-root user, dynamic `$PORT` binding.

---

## Local Development

```bash
# 1. Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Or `venv\Scripts\activate` on Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variable (optional)
export GEMINI_API_KEY="AIzaSyYourKeyHere"

# 4. Run development server
uvicorn main:app --reload --port 8080
```
Open `http://localhost:8080` in your browser.

---

## Deploy to Google Cloud Run

```bash
gcloud run deploy salon-python-tool \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars "GEMINI_API_KEY=AIzaSyYourKeyHere"
```
