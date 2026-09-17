# Google Cloud Run Deployment & Configuration Guide

This guide details the prerequisites, build workflows, and deployment commands for hosting salon efficiency tools on Google Cloud Run.

---

## 1. Prerequisites

1. **Google Cloud SDK (`gcloud`)**:
   Ensure `gcloud` is installed and authenticated:
   ```bash
   gcloud auth login
   gcloud config set project kimiiro-salon
   ```

2. **Required GCP Services**:
   Enable Cloud Run and Cloud Build APIs on the project:
   ```bash
   gcloud services enable run.googleapis.com
   gcloud services enable cloudbuild.googleapis.com
   gcloud services enable artifactregistry.googleapis.com
   ```

3. **Service Account Permissions**:
   The deployer needs:
   - `roles/run.admin`
   - `roles/iam.serviceAccountUser`
   - `roles/artifactregistry.writer`

---

## 2. Recommended Cloud Run Configuration

For efficiency tools serving salon users, the following service parameters provide optimal responsiveness with zero idle costs:

| Setting | Recommended Value | Rationale |
| :--- | :--- | :--- |
| Region | `asia-northeast1` (Tokyo) | Lowest latency for Japanese users |
| Memory | `512Mi` or `1Gi` | Sufficient for Python/FastAPI and Node servers |
| CPU | `1` | Serverless on-demand CPU allocation |
| Min Instances | `0` | Scale to zero when inactive (no idle charge) |
| Max Instances | `5` | Prevents runaway costs from traffic spikes |
| Concurrency | `80` | Handles simultaneous requests efficiently |
| Timeout | `300s` | Permits long-running LLM completions |
| Ingress | `all` | Allows external web traffic |
| Authentication | `--allow-unauthenticated` | Accessible to salon frontend iframes |

---

## 3. Direct Source Deployment (`gcloud run deploy`)

The fastest way to deploy without managing container registries manually is using Cloud Build via `--source`:

```bash
gcloud run deploy my-salon-tool \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 5 \
  --set-env-vars "NODE_ENV=production"
```

Google Cloud Build will automatically:
1. Detect the `Dockerfile` in the current directory.
2. Build the container image in Google Cloud.
3. Push it to Artifact Registry.
4. Deploy the image to a new Cloud Run revision.
5. Print the public HTTPS service URL (e.g. `https://my-salon-tool-xyz.a.run.app`).

---

## 4. Environment Variables & Secret Management

If your tool requires AI API keys (e.g., Google Gemini API, OpenAI):

### Option A: Secret Manager (Recommended for Production)
```bash
# Create secret in Google Secret Manager
echo "YOUR_GEMINI_KEY" | gcloud secrets create GEMINI_API_KEY --data-file=-

# Grant Cloud Run service account access
gcloud secrets add-iam-policy-binding GEMINI_API_KEY \
  --member="serviceAccount:service-account@kimiiro-salon.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Deploy with secret reference
gcloud run deploy my-salon-tool \
  --source . \
  --set-secrets="GEMINI_API_KEY=GEMINI_API_KEY:latest"
```

### Option B: Direct Environment Variable (Development / Fast Testing)
```bash
gcloud run deploy my-salon-tool \
  --source . \
  --set-env-vars "GEMINI_API_KEY=AIzaSyYourKeyHere"
```

---

## 5. Verifying Deployment Health

Once deployed, verify that the service is running and properly configured:

```bash
# Test health endpoint
curl -I https://my-salon-tool-xyz.a.run.app/health

# Verify absence of blocking headers
curl -s -D - https://my-salon-tool-xyz.a.run.app -o /dev/null | grep -i "x-frame-options"
```
Ensure `X-Frame-Options: DENY` is NOT returned.
