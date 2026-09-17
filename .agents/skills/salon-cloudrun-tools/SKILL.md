---
name: salon-cloudrun-tools
description: >-
  Build, deploy, and integrate Google Cloud Run efficiency tools for the salon platform,
  and share or reuse salon efficiency tools across external projects. Provides standardized
  containerization templates, postMessage integration protocols, automated Cloud Run deployment scripts,
  and Firestore tool registration.
---

# Salon Cloud Run Tools Skill

This skill provides step-by-step procedures, standardized container templates, and deployment scripts to build web tools on Google Cloud Run, seamlessly integrate them into the Kimiiro Salon Platform's efficiency tools ecosystem (`/tools`), and enable other projects to reuse or contribute efficiency tools.

---

## 1. Ecosystem Overview

The salon platform includes an Efficiency Tools hub (`/tools`) that serves both members and operators:
1. **Host Platform**: Next.js App Router deployed on Firebase Hosting (`https://kimiiro-salon.web.app`).
2. **Efficiency Tools Hub (`/tools`)**: Renders native AI tools, inline custom widgets, and external web tools embedded via sandboxed `iframe`.
3. **Cloud Run Integration**: Allows any web application (Python FastAPI/Streamlit, Node.js/Express, Go, Next.js) to run on Google Cloud Run with serverless scalability, automatic HTTPS, and secure containerization.
4. **Bi-directional PostMessage Bridge**: Embedded Cloud Run tools communicate with the host salon to save drafts directly into Firestore (`columns` or `contents`), sync themes, and trigger host notifications.
5. **Cross-Project Portability**: Tools created for the salon can be exposed via REST APIs or embedded as widgets in other projects, and tools from other projects can be published to the salon with a single registration command.

---

## 2. Quick Start Workflow

To build and deploy a new tool to Cloud Run and link it to the salon platform:

```bash
# Step 1: Choose or copy a template
cp -r .agents/skills/salon-cloudrun-tools/templates/python-fastapi my-tool
cd my-tool

# Step 2: Test locally (Port 8080)
uvicorn main:app --host 0.0.0.0 --port 8080

# Step 3: Deploy to Google Cloud Run
# (Run from project root or tool folder)
pwsh ../scripts/deploy-cloudrun.ps1 -ServiceName my-salon-tool -Region asia-northeast1

# Step 4: Register into the salon platform database
node ../scripts/register-tool.mjs --name "AI Copy Generator" --url "https://my-salon-tool-xxx.a.run.app" --category "コンテンツ制作" --role "user"
```

---

## 3. Tool Architecture Requirements

Any tool deployed to Cloud Run for the salon platform must fulfill three requirements:

### A. Iframe Embedding & Security Headers
The Cloud Run service must NOT block iframe embedding. Avoid `X-Frame-Options: DENY`. Configure `Content-Security-Policy`:
```http
Content-Security-Policy: frame-ancestors 'self' https://kimiiro-salon.web.app https://*.web.app http://localhost:3000;
```

### B. Standard Port & Health Check
Cloud Run injects the `PORT` environment variable (default: `8080`). The container must:
- Bind to `0.0.0.0:$PORT`.
- Respond with `200 OK` on `GET /health` or `GET /`.

### C. PostMessage Communication Protocol
When the user finishes generating content (e.g. an article, copy, or marketing outline), the tool can send it directly to the salon's draft system:
```javascript
window.parent.postMessage({
  type: 'SAVE_DRAFT',
  title: 'Generated Column Title',
  content: 'Article body in markdown or HTML...',
  targetCollection: 'columns' // 'columns' or 'contents'
}, '*');
```
The salon host listens for `SAVE_DRAFT`, saves the entry to Firestore (`portal_data/columns` or `portal_data/contents`), displays a success toast, and redirects the user to the editor.

---

## 4. Pre-built Templates

This skill includes production-ready templates under `templates/`:

1. **Python FastAPI (`templates/python-fastapi/`)**:
   - High-performance asynchronous API backend with an integrated Kimidori-themed responsive UI.
   - Built-in Gemini API integration for AI copy generation and content analysis.
   - Ready-to-use Dockerfile with non-root security user.
   - See [Python Template Guide](./templates/python-fastapi/README.md).

2. **Node.js Express (`templates/nodejs-express/`)**:
   - Lightweight Express server with static asset hosting and API endpoints.
   - Clean HTML5/CSS3 frontend following the Kimidori design system.
   - Alpine Linux Dockerfile for minimal image size and fast deployment.
   - See [Node.js Template Guide](./templates/nodejs-express/README.md).

---

## 5. Deployment Scripts

Helper scripts are located in `scripts/`:

| Script | Purpose |
| :--- | :--- |
| `scripts/deploy-cloudrun.ps1` | PowerShell script to build and deploy container to Cloud Run |
| `scripts/deploy-cloudrun.sh` | Bash script for Linux/macOS environments |
| `scripts/register-tool.mjs` | Node.js script to register/update tools in Firestore `custom_tools` |
| `scripts/test-tool-connection.mjs` | Health and iframe header validation utility |

### Deploying via PowerShell
```powershell
.\scripts\deploy-cloudrun.ps1 `
  -ToolDir "templates/python-fastapi" `
  -ServiceName "salon-ai-writer" `
  -ProjectId "kimiiro-salon" `
  -Region "asia-northeast1"
```

### Registering to Firestore
```bash
node scripts/register-tool.mjs \
  --name "AIセールスコピー作成スタジオ" \
  --url "https://salon-ai-writer-xyz.a.run.app" \
  --category "コンテンツ制作" \
  --role "user" \
  --order 10
```

---

## 6. Reusing Salon Efficiency Tools in Other Projects

Efficiency tools built for the salon can be utilized by external projects in two primary ways:

### Method 1: Iframe Widget Embedding
Include the deployed Cloud Run tool into any web application:
```html
<iframe
  src="https://salon-ai-writer-xyz.a.run.app"
  style="width: 100%; height: 800px; border: none; border-radius: 12px;"
  sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
></iframe>

<script>
window.addEventListener('message', (event) => {
  if (event.data?.type === 'SAVE_DRAFT') {
    console.log('[External App] Received draft:', event.data.title, event.data.content);
    // Handle draft in your external application
  }
});
</script>
```

### Method 2: Headless REST API
Cloud Run tools provide direct REST endpoints for automated pipelines, external CMS integration, or command-line scripts:
```bash
curl -X POST https://salon-ai-writer-xyz.a.run.app/api/generate \
  -H "Content-Type: application/json" \
  -d '{"theme": "副業の始め方", "style": "SNSキャッチコピー"}'
```

---

## 7. Reference Documents

- [Platform Architecture & Schema](./references/architecture.md): Firestore schemas, role permissions, and iframe specifications.
- [PostMessage Protocol Specification](./references/postmessage-spec.md): Complete event catalog and payloads.
- [Cloud Run Deployment Guide](./references/cloudrun-deploy-guide.md): IAM, environment variables, custom domains, and cost optimization.
- [Cross-Project Integration Guide](./references/cross-project-sharing.md): Best practices for sharing tools across teams and repositories.
