# Node.js Express Efficiency Tool Template

A lightweight, production-ready Express template for building efficiency tools deployed to Google Cloud Run and integrated into the Kimiiro Salon platform.

---

## Features

- **Express 4 Server**: Fast and minimal web service.
- **Pre-configured CSP Headers**: Automatically enables iframe embedding from `https://kimiiro-salon.web.app` and localhost.
- **Kimidori Themed UI**: Matches the salon's visual standards.
- **PostMessage Integration**: Dispatches `SAVE_DRAFT` events directly to the salon host.
- **Cloud Run Optimized Dockerfile**: Minimal Alpine Linux image, non-root user, dynamic `$PORT` binding.

---

## Local Development

```bash
# 1. Install dependencies
npm install

# 2. Set environment variable (optional)
export GEMINI_API_KEY="AIzaSyYourKeyHere"

# 3. Run development server
npm run dev
```
Open `http://localhost:8080` in your browser.

---

## Deploy to Google Cloud Run

```bash
gcloud run deploy salon-node-tool \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars "GEMINI_API_KEY=AIzaSyYourKeyHere"
```
