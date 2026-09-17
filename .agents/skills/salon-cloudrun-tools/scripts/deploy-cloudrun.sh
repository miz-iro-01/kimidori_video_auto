#!/usr/bin/env bash
# Deploy an efficiency tool to Google Cloud Run for the Kimiiro Salon Platform.

set -euo pipefail

TOOL_DIR="${1:-.}"
SERVICE_NAME="${2:-salon-efficiency-tool}"
PROJECT_ID="${3:-kimiiro-salon}"
REGION="${4:-asia-northeast1}"
MEMORY="${5:-512Mi}"

echo "======================================================"
echo "[SALON CLOUD RUN DEPLOYMENT TOOL]"
echo "Service Name : ${SERVICE_NAME}"
echo "Project ID   : ${PROJECT_ID}"
echo "Region       : ${REGION}"
echo "Directory    : ${TOOL_DIR}"
echo "======================================================"

if [ ! -d "${TOOL_DIR}" ]; then
  echo "[ERROR] Directory '${TOOL_DIR}' not found."
  exit 1
fi

if [ ! -f "${TOOL_DIR}/Dockerfile" ]; then
  echo "[ERROR] No Dockerfile found in '${TOOL_DIR}'."
  exit 1
fi

echo "[INFO] Setting active project to ${PROJECT_ID}..."
gcloud config set project "${PROJECT_ID}"

echo "[INFO] Deploying to Cloud Run (this may take 1-3 minutes)..."
SERVICE_URL=$(gcloud run deploy "${SERVICE_NAME}" \
  --source "${TOOL_DIR}" \
  --region "${REGION}" \
  --memory "${MEMORY}" \
  --min-instances 0 \
  --max-instances 5 \
  --timeout 300s \
  --allow-unauthenticated \
  --format "value(status.url)")

echo "======================================================"
echo "[SUCCESS] Tool successfully deployed to Cloud Run!"
echo "Service URL: ${SERVICE_URL}"
echo "======================================================"
echo "[NEXT STEP] Register this URL into the Salon platform with:"
echo "node scripts/register-tool.mjs --name \"${SERVICE_NAME}\" --url \"${SERVICE_URL}\""
