/**
 * BSupervisor demo smoke tests.
 *
 * Run locally:
 *   ~/Works/_infra/scripts/demo-up-local.sh BSupervisor
 *   DEMO_E2E_BASE_URL=http://localhost:19000 \
 *   DEMO_E2E_API_URL=http://localhost:19000 \
 *     pnpm test:e2e --grep @demo
 */

import { runDemoSmokeSuite } from '@bsvibe/demo/testing';

runDemoSmokeSuite({
  product: 'BSupervisor',
  baseUrl: process.env.DEMO_E2E_BASE_URL ?? 'http://localhost:19000',
  apiUrl: process.env.DEMO_E2E_API_URL ?? 'http://localhost:19000',
});
