<#
.SYNOPSIS
  Deploy an efficiency tool to Google Cloud Run for the Kimiiro Salon Platform.

.DESCRIPTION
  This script builds and deploys a containerized tool directory to Google Cloud Run,
  configures standard environment parameters, and returns the public service URL.

.PARAMETER ToolDir
  Directory containing the tool code and Dockerfile (Default: .)

.PARAMETER ServiceName
  Name of the Cloud Run service (Default: salon-efficiency-tool)

.PARAMETER ProjectId
  Google Cloud Project ID (Default: kimiiro-salon)

.PARAMETER Region
  Deployment region (Default: asia-northeast1)

.PARAMETER Memory
  Container memory limit (Default: 512Mi)

.PARAMETER AllowUnauthenticated
  Allow public access for iframe embedding (Default: $true)
#>

param(
  [string]$ToolDir = ".",
  [string]$ServiceName = "salon-efficiency-tool",
  [string]$ProjectId = "kimiiro-salon",
  [string]$Region = "asia-northeast1",
  [string]$Memory = "512Mi",
  [switch]$AllowUnauthenticated = $true
)

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "[SALON CLOUD RUN DEPLOYMENT TOOL]" -ForegroundColor Cyan
Write-Host "Service Name : $ServiceName"
Write-Host "Project ID   : $ProjectId"
Write-Host "Region       : $Region"
Write-Host "Directory    : $ToolDir"
Write-Host "======================================================" -ForegroundColor Cyan

# Verify directory exists
if (-not (Test-Path $ToolDir)) {
  Write-Error "[ERROR] Directory '$ToolDir' not found."
  exit 1
}

# Verify Dockerfile exists
if (-not (Test-Path (Join-Path $ToolDir "Dockerfile"))) {
  Write-Error "[ERROR] No Dockerfile found in '$ToolDir'."
  exit 1
}

# Set active GCP Project
Write-Host "[INFO] Setting active project to $ProjectId..." -ForegroundColor Yellow
& gcloud config set project $ProjectId
if ($LASTEXITCODE -ne 0) {
  Write-Error "[ERROR] Failed to set GCP project. Ensure you are logged in via 'gcloud auth login'."
  exit 1
}

# Build arguments array
$deployArgs = @(
  "run", "deploy", $ServiceName,
  "--source", $ToolDir,
  "--region", $Region,
  "--memory", $Memory,
  "--min-instances", "0",
  "--max-instances", "5",
  "--timeout", "300s",
  "--format", "value(status.url)"
)

if ($AllowUnauthenticated) {
  $deployArgs += "--allow-unauthenticated"
}

Write-Host "[INFO] Deploying to Cloud Run (this may take 1-3 minutes)..." -ForegroundColor Yellow
$serviceUrl = & gcloud @deployArgs

if ($LASTEXITCODE -eq 0 -and $serviceUrl) {
  Write-Host "======================================================" -ForegroundColor Green
  Write-Host "[SUCCESS] Tool successfully deployed to Cloud Run!" -ForegroundColor Green
  Write-Host "Service URL: $serviceUrl" -ForegroundColor Green
  Write-Host "======================================================" -ForegroundColor Green
  Write-Host "[NEXT STEP] Register this URL into the Salon platform with:" -ForegroundColor Cyan
  Write-Host "node scripts/register-tool.mjs --name `"$ServiceName`" --url `"$serviceUrl`"" -ForegroundColor White
} else {
  Write-Error "[ERROR] Deployment failed. Check the logs above."
  exit 1
}
