# Cross-Project Sharing & Tool Reuse Guide

This guide explains how external projects can consume efficiency tools hosted on Cloud Run, and conversely, how tools created in other projects can be seamlessly integrated into the Kimiiro Salon platform.

---

## 1. Sharing Modes

Cloud Run tools deployed under the salon ecosystem support three integration modes across external projects:

```
+--------------------------------------------------------------------+
|                       Google Cloud Run Service                     |
|                   (e.g., AI Copywriting Studio)                    |
+---------------------------------+----------------------------------+
                                  |
         +------------------------+------------------------+
         |                                                 |
         v                                                 v
  [Mode 1: Iframe Widget]                        [Mode 2: REST API]
  - Kimiiro Salon Portal                         - Next.js / Astro App
  - External Admin Dashboard                     - Python Batch Scraper
  - Notion / Coda Web Embed                      - Slack / Discord Bot
```

---

## 2. Mode 1: Embedding as an Iframe Widget

Any project (e.g. an external client dashboard, a secondary salon, or a marketing landing page) can embed the Cloud Run tool.

### HTML Embed Snippet
```html
<div class="tool-container" style="width: 100%; max-width: 1200px; margin: 0 auto;">
  <iframe
    id="salon-tool-frame"
    src="https://my-salon-tool-xyz.a.run.app"
    style="width: 100%; height: 750px; border: 1px solid #e2e8f0; border-radius: 12px;"
    sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals allow-downloads"
  ></iframe>
</div>
```

### Capturing Generated Content in the Host Project
If the user clicks "下書きを転送" inside the tool, your external project can intercept the generated text:
```javascript
window.addEventListener('message', (event) => {
  // Optional: verify origin
  if (!event.origin.includes('run.app')) return;

  if (event.data && event.data.type === 'SAVE_DRAFT') {
    const { title, content, targetCollection } = event.data;
    console.log('[External App] Draft received:', title);

    // Save into your project database, display modal, or trigger workflow
    saveToMyProjectDatabase({ title, content, type: targetCollection });
  }
});
```

---

## 3. Mode 2: Headless REST API Integration

Cloud Run tools packaged with this skill include JSON REST endpoints. Other projects can make standard HTTP requests to execute AI generation or analysis without rendering the UI.

### Endpoint: `POST /api/generate`
Headers: `Content-Type: application/json`

#### Request Body
```json
{
  "theme": "個人開発者のためのSNS集客戦略",
  "category": "catchphrase",
  "numVariants": 3
}
```

#### Response Body
```json
{
  "status": "success",
  "output": "1. 30日でフォロワー1,000人達成の具体的手順...\n2. 開発だけじゃ売れない？集客と並行する黄金ロードマップ...\n3. ゼロから始めるコミュニティ型ローンチ戦略..."
}
```

#### Example Usage from a Python Project
```python
import requests

def generate_marketing_copy(theme: str) -> str:
    url = "https://my-salon-tool-xyz.a.run.app/api/generate"
    response = requests.post(url, json={"theme": theme, "category": "catchphrase"})
    response.raise_for_status()
    return response.json()["output"]

print(generate_marketing_copy("AIツールの活用術"))
```

#### Example Usage from a Next.js / Node.js Project
```typescript
export async function getAiSuggestions(theme: string) {
  const res = await fetch('https://my-salon-tool-xyz.a.run.app/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ theme, category: 'summary' }),
    next: { revalidate: 3600 }
  });
  const data = await res.json();
  return data.output;
}
```

---

## 4. Publishing an External Project's Tool to the Salon

If an external team develops a new tool in their own repository and wants it visible within the Kimiiro Salon's `/tools` section:

1. Deploy the external tool to Google Cloud Run (ensure `frame-ancestors` includes `https://kimiiro-salon.web.app`).
2. Run the registration script from this skill:
   ```bash
   node scripts/register-tool.mjs \
     --name "外部リンク分析アシスタント" \
     --url "https://external-analysis-tool-xyz.a.run.app" \
     --category "業務効率化" \
     --role "user"
   ```
3. The tool immediately appears in the salon portal tabs for all members without requiring a redeployment of the salon frontend!
