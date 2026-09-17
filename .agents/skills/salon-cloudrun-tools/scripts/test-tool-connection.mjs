#!/usr/bin/env node
/**
 * Test connectivity, health endpoint, and iframe security headers for a Cloud Run tool.
 * 
 * Usage:
 *   node scripts/test-tool-connection.mjs https://my-tool.a.run.app
 */

const targetUrl = process.argv[2];

if (!targetUrl) {
  console.error('[ERROR] Target URL required.');
  console.log('Usage: node scripts/test-tool-connection.mjs <service-url>');
  process.exit(1);
}

async function testConnection() {
  console.log(`[INFO] Testing service: ${targetUrl}...`);

  try {
    const res = await fetch(targetUrl, { method: 'GET', redirect: 'follow' });
    console.log(`[STATUS] HTTP ${res.status} ${res.statusText}`);

    const xFrame = res.headers.get('x-frame-options');
    const csp = res.headers.get('content-security-policy');

    console.log('------------------------------------------------------');
    console.log('Security Header Inspection:');
    if (xFrame) {
      console.warn(`[WARNING] 'X-Frame-Options' header detected: '${xFrame}'`);
      if (xFrame.toLowerCase().includes('deny') || xFrame.toLowerCase().includes('sameorigin')) {
        console.error('[FAIL] This tool will NOT load inside the Salon iframe! Remove X-Frame-Options or set to ALLOWALL.');
      }
    } else {
      console.log(`[PASS] No restrictive 'X-Frame-Options' header found.`);
    }

    if (csp) {
      console.log(`[INFO] 'Content-Security-Policy': ${csp}`);
      if (csp.includes('frame-ancestors')) {
        console.log(`[PASS] 'frame-ancestors' directive detected.`);
      }
    } else {
      console.log(`[INFO] No CSP restrictions detected.`);
    }
    console.log('------------------------------------------------------');

    // Test /health endpoint
    const healthUrl = targetUrl.replace(/\/+$/, '') + '/health';
    try {
      const healthRes = await fetch(healthUrl);
      if (healthRes.ok) {
        const body = await healthRes.json().catch(() => null);
        console.log(`[PASS] /health endpoint responded 200 OK:`, body);
      } else {
        console.log(`[INFO] /health endpoint returned ${healthRes.status}. (Optional)`);
      }
    } catch {
      console.log(`[INFO] No dedicated /health endpoint found.`);
    }

    console.log('======================================================');
    console.log('[SUCCESS] Verification complete. Ready for salon integration.');
    console.log('======================================================');
  } catch (err) {
    console.error(`[ERROR] Failed to connect to ${targetUrl}:`, err.message);
    process.exit(1);
  }
}

testConnection();
