#!/usr/bin/env node
/**
 * Register or update a Cloud Run Efficiency Tool in the Kimiiro Salon Firestore database.
 * 
 * Usage:
 *   node scripts/register-tool.mjs --name "AIコピー作成" --url "https://my-tool.a.run.app" --category "コンテンツ制作" --role "user"
 */

import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

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

if (!fs.existsSync(saPath)) {
  console.error(`[ERROR] Service account file not found at: ${saPath}`);
  console.error('Ensure service-account.json exists in the project root to perform Firestore writes.');
  process.exit(1);
}

async function register() {
  console.log('[INFO] Connecting to Firestore...');
  const { default: admin } = await import('firebase-admin');
  
  if (!admin.apps.length) {
    const serviceAccount = JSON.parse(fs.readFileSync(saPath, 'utf8'));
    admin.initializeApp({
      credential: admin.credential.cert(serviceAccount)
    });
  }

  const db = admin.firestore();

  // Generate ID or find existing by URL
  let toolId = `cr_${Date.now()}`;
  const customToolsRef = db.collection('custom_tools');
  const existingSnap = await customToolsRef.where('embedUrl', '==', embedUrl).get();

  if (!existingSnap.empty) {
    toolId = existingSnap.docs[0].id;
    console.log(`[INFO] Found existing tool registration with ID: ${toolId}. Updating...`);
  } else {
    console.log(`[INFO] Registering new tool with ID: ${toolId}...`);
  }

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

  // 1. Write to custom_tools collection
  await customToolsRef.doc(toolId).set(toolData, { merge: true });
  console.log(`[OK] Saved to custom_tools/${toolId}`);

  // 2. Sync to portal_data/custom_tools
  const portalDocRef = db.collection('portal_data').doc('custom_tools');
  const portalSnap = await portalDocRef.get();
  let externalItems = [];
  if (portalSnap.exists && Array.isArray(portalSnap.data()?.externalItems)) {
    externalItems = portalSnap.data().externalItems;
  }

  const existingIdx = externalItems.findIndex(i => i.id === toolId || i.embedUrl === embedUrl);
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
}

register().catch(err => {
  console.error('[ERROR] Registration failed:', err);
  process.exit(1);
});
