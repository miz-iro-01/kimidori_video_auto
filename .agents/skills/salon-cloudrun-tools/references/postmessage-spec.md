# Salon Platform PostMessage Integration Specification

This document specifies the message protocol between the Kimiiro Salon host application and embedded Cloud Run efficiency tools.

---

## 1. Overview

Because the Cloud Run tool runs on a separate origin (e.g., `https://my-tool-xxx.a.run.app`) from the salon host (`https://kimiiro-salon.web.app`), direct DOM or JavaScript access is prevented by the Same-Origin Policy.
Cross-origin communication is conducted securely via `window.postMessage`.

---

## 2. Supported Events (Tool -> Salon Host)

### Event: `SAVE_DRAFT`
Saves generated content into the salon portal's Firestore database as a draft article or column.

#### Payload Schema
```typescript
interface SaveDraftMessage {
  type: 'SAVE_DRAFT';               // Or action: 'SAVE_DRAFT'
  title: string;                    // Title of the article/column
  content: string;                  // Article body (Markdown or HTML)
  targetCollection?: 'columns' | 'contents'; // Target Firestore collection (default: 'contents')
  category?: string;                // Optional category tag (e.g., 'マーケティング')
  harmsTag?: 'H' | 'A' | 'R' | 'M' | 'S'; // Optional HARMS psychological category
}
```

#### Client Example (Inside Cloud Run Tool)
```javascript
function sendDraftToSalon(title, content, target = 'columns') {
  if (window.parent && window.parent !== window) {
    window.parent.postMessage({
      type: 'SAVE_DRAFT',
      title: title,
      content: content,
      targetCollection: target
    }, '*');
  } else {
    console.warn('[Tool] Running in standalone mode. Parent window not found.');
  }
}
```

#### Host Behavior
Upon receiving `SAVE_DRAFT`:
1. Validates the incoming payload fields (`title`, `content`).
2. Creates an item ID (`col_<timestamp>` for columns, `cnt_<timestamp>` for contents).
3. Merges the document into Firestore:
   - `portal_data/{targetCollection}`
   - `portal_data_{targetCollection}/{itemId}`
4. Displays a toast notification: `「[Title]」を下書き保存しました！編集画面へ移動します...`
5. Navigates the operator to `/columns` or `/contents` draft tab.

---

### Event: `SHOW_TOAST`
Requests the host salon to display a toast notification in the main viewport.

#### Payload Schema
```typescript
interface ShowToastMessage {
  type: 'SHOW_TOAST';
  message: string;
  variant?: 'success' | 'error' | 'info';
}
```

---

## 3. Supported Events (Salon Host -> Tool)

When an embedded Cloud Run tool initializes, it can listen for contextual data from the salon host.

### Event: `INIT_CONTEXT`
Provides the tool with user context, active theme, and permissions.

#### Payload Schema
```typescript
interface InitContextMessage {
  type: 'INIT_CONTEXT';
  userEmail: string;
  role: 'operator' | 'user';
  theme: 'light' | 'dark';
  salonUrl: string;
}
```

#### Tool Listener Example
```javascript
window.addEventListener('message', (event) => {
  // Validate sender origin if needed
  if (!event.origin.includes('kimiiro-salon') && !event.origin.includes('localhost')) {
    return;
  }

  if (event.data?.type === 'INIT_CONTEXT') {
    const { userEmail, role, theme } = event.data;
    console.log('[Tool] Connected to salon host. Active user:', userEmail);
    applyTheme(theme);
  }
});
```

---

## 4. Error Handling & Standalone Mode

Tools must be designed to work both **inside an iframe** and **as standalone applications**:
- Check `window.parent !== window` before dispatching `postMessage`.
- If running standalone (e.g. accessed directly by URL or in another project), provide a fallback action, such as downloading the content as a markdown file or copying it to the clipboard.
