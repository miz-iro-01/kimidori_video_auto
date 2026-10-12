#!/usr/bin/env node
/**
 * Register or update a Cloud Run Efficiency Tool in the Kimiiro Salon Firestore database.
 * Supports both Firebase Admin SDK (service-account.json) and gcloud auth token fallback (Firestore REST API).
 * 
 * Usage:
 *   node scripts/register-tool.mjs --name "KIMIDORI YouTube Auto" --url "https://my-tool.a.run.app" --category "コンテンツ制作" --role "user"
 */

import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Simple CLI arg parser
const args = process.argv.slice(2);
function getArg(name, defaultValue = '') {
  const idx = args.indexOf(`--${name}`);
  if (idx !== -1 && idx + 1 < args.length) return args[idx + 1];
  return defaultValue;
}

const toolName = getArg('name');
const embedUrl = getArg('url');
const category = getArg('category', '業務効率化');
const targetRole = getArg('role', 'user'); // 'user' | 'operator'
const sortOrder = parseInt(getArg('order', '10'), 10);
const description = getArg('desc', 'Cloud Run上で稼働するサロン効率化ツール');
const status = getArg('status', 'published'); // 'published' | 'draft'

if (!toolName || !embedUrl) {
  console.error('[ERROR] Missing required arguments: --name and --url');
  console.log('Usage: node scripts/register-tool.mjs --name "<Tool Name>" --url "<Cloud Run URL>" [--category "<Cat>"] [--role "user"|"operator"]');
  process.exit(1);
}

if (!embedUrl.startsWith('http')) {
  console.error('[ERROR] The --url argument must be a valid HTTP/HTTPS URL.');
  process.exit(1);
}

// Locate service account json
const rootDir = path.resolve(__dirname, '../../..');
const saPath = path.join(rootDir, 'service-account.json');

// Check gcloud token
function getGcloudAccessToken() {
  try {
    return execSync('gcloud auth print-access-token', { encoding: 'utf8' }).trim();
  } catch (e) {
    return null;
  }
}

async function registerViaRest(token, toolData, embedUrl) {
  const projectId = 'kimiiro-salon';
  const baseUrl = `https://firestore.googleapis.com/v1/projects/${projectId}/databases/(default)/documents`;

  const headers = {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };

  function toFirestoreValue(val) {
    if (typeof val === 'string') return { stringValue: val };
    if (typeof val === 'number') return { integerValue: val.toString() };
    if (typeof val === 'boolean') return { booleanValue: val };
    if (Array.isArray(val)) return { arrayValue: { values: val.map(toFirestoreValue) } };
    if (typeof val === 'object' && val !== null) {
      const fields = {};
      for (const [k, v] of Object.entries(val)) {
        fields[k] = toFirestoreValue(v);
      }
      return { mapValue: { fields } };
    }
    return { nullValue: null };
  }

  function fromFirestoreValue(val) {
    if (!val) return null;
    if ('stringValue' in val) return val.stringValue;
    if ('integerValue' in val) return parseInt(val.integerValue, 10);
    if ('booleanValue' in val) return val.booleanValue;
    if ('arrayValue' in val) return (val.arrayValue.values || []).map(fromFirestoreValue);
    if ('mapValue' in val) {
      const res = {};
      for (const [k, v] of Object.entries(val.mapValue.fields || {})) {
        res[k] = fromFirestoreValue(v);
      }
      return res;
    }
    return null;
  }

  console.log('[INFO] Checking existing tool entries via Firestore REST API...');
  let toolId = toolData.id;
  try {
    const listRes = await fetch(`${baseUrl}/custom_tools`, { headers });
    if (listRes.ok) {
      const listData = await listRes.json();
      const docs = listData.documents || [];
      for (const doc of docs) {
        const docFields = {};
        for (const [k, v] of Object.entries(doc.fields || {})) {
          docFields[k] = fromFirestoreValue(v);
        }
        if (docFields.embedUrl === embedUrl) {
          toolId = doc.name.split('/').pop();
          console.log(`[INFO] Found existing tool registration with ID: ${toolId}. Updating...`);
          break;
        }
      }
    }
  } catch (e) {
    console.warn('[WARN] Could not query existing tools:', e.message);
  }

  toolData.id = toolId;

  // 1. Write to custom_tools/{toolId}
  const toolFields = {};
  for (const [k, v] of Object.entries(toolData)) {
    toolFields[k] = toFirestoreValue(v);
  }

  const patchRes = await fetch(`${baseUrl}/custom_tools/${toolId}`, {
    method: 'PATCH',
    headers,
    body: JSON.stringify({ fields: toolFields })
  });

  if (!patchRes.ok) {
    const errText = await patchRes.text();
    throw new Error(`Failed to write custom_tools/${toolId}: ${errText}`);
  }
  console.log(`[OK] Saved to custom_tools/${toolId}`);

  // 2. Sync to portal_data/custom_tools
  let externalItems = [];
  try {
    const portalRes = await fetch(`${baseUrl}/portal_data/custom_tools`, { headers });
    if (portalRes.ok) {
      const portalDoc = await portalRes.json();
      const rawItems = portalDoc.fields?.externalItems;
      if (rawItems) {
        externalItems = fromFirestoreValue(rawItems) || [];
      }
    }
  } catch (e) {
    console.warn('[WARN] Could not fetch portal_data/custom_tools:', e.message);
  }

  const existingIdx = externalItems.findIndex(i => i.id === toolId || i.embedUrl === embedUrl);
  if (existingIdx >= 0) {
    externalItems[existingIdx] = { ...externalItems[existingIdx], ...toolData };
  } else {
    externalItems.push(toolData);
  }

  externalItems.sort((a, b) => (a.sortOrder || 0) - (b.sortOrder || 0));

  const portalFields = {
    externalItems: toFirestoreValue(externalItems),
    updatedAt: toFirestoreValue(new Date().toISOString())
  };

  const portalPatchRes = await fetch(`${baseUrl}/portal_data/custom_tools`, {
    method: 'PATCH',
    headers,
    body: JSON.stringify({ fields: portalFields })
  });

  if (!portalPatchRes.ok) {
    const errText = await portalPatchRes.text();
    throw new Error(`Failed to sync portal_data/custom_tools: ${errText}`);
  }
  console.log(`[OK] Synced to portal_data/custom_tools (Total active tools: ${externalItems.length})`);
  console.log('======================================================');
  console.log('[SUCCESS] Tool successfully registered in Kimiiro Salon!');
  console.log(`Tool Name : ${toolData.toolName}`);
  console.log(`Target URL: ${toolData.embedUrl}`);
  console.log(`Role      : ${toolData.targetRole}`);
  console.log(`Category  : ${toolData.category}`);
  console.log(`Status    : ${toolData.status}`);
  console.log('It is now immediately available in /tools on the platform.');
  console.log('======================================================');
}

async function register() {
  const toolId = `cr_${Date.now()}`;
  const toolData = {
    id: toolId,
    toolName: toolName.trim(),
    embedUrl: embedUrl.trim(),
    category: category.trim(),
    targetRole: targetRole === 'operator' ? 'operator' : 'user',
    status: status === 'draft' ? 'draft' : 'published',
    sortOrder: isNaN(sortOrder) ? 10 : sortOrder,
    description: description.trim(),
    updatedAt: new Date().toISOString(),
    createdAt: new Date().toISOString()
  };

  // Check if service-account.json exists
  if (fs.existsSync(saPath)) {
    console.log('[INFO] Connecting to Firestore via service-account.json...');
    const { default: admin } = await import('firebase-admin');
    if (!admin.apps.length) {
      const serviceAccount = JSON.parse(fs.readFileSync(saPath, 'utf8'));
      admin.initializeApp({
        credential: admin.credential.cert(serviceAccount)
      });
    }

    const db = admin.firestore();
    const customToolsRef = db.collection('custom_tools');
    const existingSnap = await customToolsRef.where('embedUrl', '==', embedUrl).get();

    let finalToolId = toolId;
    if (!existingSnap.empty) {
      finalToolId = existingSnap.docs[0].id;
      console.log(`[INFO] Found existing tool registration with ID: ${finalToolId}. Updating...`);
    } else {
      console.log(`[INFO] Registering new tool with ID: ${finalToolId}...`);
    }
    toolData.id = finalToolId;

    await customToolsRef.doc(finalToolId).set(toolData, { merge: true });
    console.log(`[OK] Saved to custom_tools/${finalToolId}`);

    const portalDocRef = db.collection('portal_data').doc('custom_tools');
    const portalSnap = await portalDocRef.get();
    let externalItems = [];
    if (portalSnap.exists && Array.isArray(portalSnap.data()?.externalItems)) {
      externalItems = portalSnap.data().externalItems;
    }

    const existingIdx = externalItems.findIndex(i => i.id === finalToolId || i.embedUrl === embedUrl);
    if (existingIdx >= 0) {
      externalItems[existingIdx] = { ...externalItems[existingIdx], ...toolData };
    } else {
      externalItems.push(toolData);
    }

    externalItems.sort((a, b) => (a.sortOrder || 0) - (b.sortOrder || 0));

    await portalDocRef.set({
      externalItems: externalItems,
      updatedAt: new Date().toISOString()
    }, { merge: true });

    console.log(`[OK] Synced to portal_data/custom_tools (Total active tools: ${externalItems.length})`);
    console.log('======================================================');
    console.log('[SUCCESS] Tool successfully registered in Kimiiro Salon!');
    console.log(`Tool Name : ${toolData.toolName}`);
    console.log(`Target URL: ${toolData.embedUrl}`);
    console.log(`Role      : ${toolData.targetRole}`);
    console.log(`Category  : ${toolData.category}`);
    console.log(`Status    : ${toolData.status}`);
    console.log('It is now immediately available in /tools on the platform.');
    console.log('======================================================');
  } else {
    // Fallback: gcloud auth token via REST API
    const token = getGcloudAccessToken();
    if (!token) {
      console.error(`[ERROR] service-account.json not found and unable to get gcloud auth token.`);
      process.exit(1);
    }
    console.log('[INFO] service-account.json not found. Using gcloud authenticated user token with Firestore REST API...');
    await registerViaRest(token, toolData, embedUrl);
  }
}

register().catch(err => {
  console.error('[ERROR] Registration failed:', err);
  process.exit(1);
});
