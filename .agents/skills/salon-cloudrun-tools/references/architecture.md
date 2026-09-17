# Salon Platform Tools Architecture

This document describes the internal architecture of the Efficiency Tools (`/tools`) feature within the Kimiiro Salon platform, including data models, iframe sandbox restrictions, and security policies.

---

## 1. Component Overview

The salon tools system consists of the following components:

- **Tools Hub (`src/app/(portal)/tools/page.tsx`)**:
  The central dashboard for members and administrators. Contains:
  - Dynamic Tool Selection Tabs for registered Cloud Run tools and native AI assistants.
  - Full-screen sandboxed iframe container for active Cloud Run tools.
  - Built-in AI copywriting assistant (Catchphrase, Summary, Ideas).
  - Admin management modal for adding, modifying, and ordering Cloud Run tools.
  - Architecture and developer guides.

- **External Tool Manager (`src/components/portal/ExternalToolManager.tsx`)**:
  Administrative panel for managing external tools, URLs, target roles (`operator` vs `user`), and sorting order.

- **Operator Tool Viewer (`src/components/portal/OperatorToolViewer.tsx`)**:
  Dedicated full-screen workspace for salon operators. Listens to `postMessage` events from embedded Cloud Run tools to automatically capture generated drafts.

- **HARMS Diagnostic Tool (`src/components/portal/HarmsDiagnosticTool.tsx`)**:
  Proprietary psychology-based diagnostic tool evaluating Health, Ambition, Relation, Money, and Self.

---

## 2. Firestore Data Schemas

External Cloud Run tools are stored across two Firestore targets for redundancy and instant synchronization:

### Collection: `custom_tools/{toolId}`
Document ID: `cr_<timestamp>` or `tool_ext_<id>`

```typescript
export interface CustomExternalTool {
  id: string;             // Unique ID (e.g., 'cr_1741543200000')
  toolName: string;       // Display name shown in tabs
  embedUrl: string;       // HTTPS Cloud Run service URL
  targetRole: 'operator' | 'user'; // Target audience
  status: 'published' | 'draft';   // Visibility state
  sortOrder: number;      // Ascending tab sort index
  description?: string;   // Tool summary
  category?: string;      // Category label (e.g., 'コンテンツ制作', '思考整理')
  createdAt?: string;     // ISO 8601 timestamp
  updatedAt?: string;     // ISO 8601 timestamp
}
```

### Document: `portal_data/custom_tools`
Field: `externalItems: CustomExternalTool[]`
- Cached array used for bulk client-side hydration and offline fallback.

---

## 3. Iframe Sandbox Policy

The host platform embeds Cloud Run tools using the following HTML attributes:

```html
<iframe
  src="https://my-tool-service.a.run.app"
  title="My Tool"
  style="width: 100%; height: calc(100vh - 180px); min-height: 720px; border: 1px solid var(--border-color); border-radius: 14px; background: white;"
  sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals allow-downloads"
/>
```

### Sandbox Capabilities Granted
- `allow-scripts`: Enables JavaScript execution for dynamic UI.
- `allow-same-origin`: Allows tools to manage their own localStorage and session cookies under their Cloud Run origin.
- `allow-forms`: Enables form submissions and file uploads.
- `allow-popups`: Permits opening external links or OAuth popups in new tabs.
- `allow-modals`: Allows `window.alert`, `window.confirm`, and HTML dialogs.
- `allow-downloads`: Permits exporting CSV, JSON, or text files directly to the client machine.

### Sandbox Restrictions Enforced
- `allow-top-navigation` is **omitted**: The embedded tool cannot hijack or redirect the parent salon window. Navigation must be requested via `postMessage`.

---

## 4. Theme & Design Consistency

To maintain visual harmony with the Kimiiro Salon interface, embedded tools should respect the Kimidori palette:

| Element | CSS Variable / Hex | Usage |
| :--- | :--- | :--- |
| Primary Accent | `#84cc16` (`var(--kimidori-500)`) | Primary buttons, active tabs, focus states |
| Primary Dark | `#65a30d` (`var(--kimidori-600)`) | Button hover states, prominent titles |
| Primary Deep | `#166534` (`var(--kimidori-900)`) | Heading text on light cards |
| Background Soft | `#f7fee7` (`var(--kimidori-50)`) | Light tinted background, notification banners |
| Surface Light | `#ffffff` | Card surfaces in light theme |
| Surface Dark | `#1e293b` | Card surfaces in dark theme |
| Border Color | `rgba(226, 232, 240, 0.8)` | Subtle card dividers |
