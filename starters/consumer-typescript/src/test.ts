import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { run, PRODUCT, CAPABILITY, SOURCE } from './client';

for (const scenario of ['pass', 'receipt', 'payment', 'expensive', 'wrong-service', 'wrong-receipt', 'overcharged', 'failed-receipt', 'timeout', 'discover']) {
  test(scenario, async () => {
    const directory = await mkdtemp(join(tmpdir(), 'aimarket-client-'));
    let calls = 0;
    try {
      await writeFile(join(directory, 'input.json'), '{}');
      const fetchFn: typeof fetch = async (url, init) => {
        if (String(url).includes('/search?')) return Response.json({ matches: [{
          product_id: PRODUCT, capability_id: scenario === 'wrong-service' ? 'other' : CAPABILITY,
          source_hub: SOURCE, routed_price_usd: scenario === 'expensive' ? 2 : 0.001,
          trust_score: 0.8, p50_latency_ms: 100,
        }] });
        if (String(url).endsWith('/invoke')) {
          calls++;
          assert.equal(JSON.parse(String(init?.body)).max_price_usd, 0.01);
          if (scenario === 'timeout') throw new Error('Lost response');
          if (scenario === 'payment') return Response.json({}, { status: 402 });
          return Response.json({ success: true, receipt: { receipt_id: 'fixture', product_id: PRODUCT,
            capability_id: scenario === 'wrong-receipt' ? 'other' : CAPABILITY,
            success: scenario !== 'failed-receipt', price_usd: scenario === 'overcharged' ? 1 : 0.001,
          } });
        }
        assert.ok(String(url).endsWith('/receipts/verify'));
        return Response.json({ valid: scenario !== 'receipt', signer_matches_live_key: true, policy_requires_pq: false });
      };
      const options = { invoke: scenario !== 'discover', directory, fetch: fetchFn };
      if (scenario === 'pass' || scenario === 'discover') await run(options);
      else await assert.rejects(run(options));
      assert.equal(calls, ['expensive', 'wrong-service', 'discover'].includes(scenario) ? 0 : 1);
      if (scenario !== 'discover') {
        const previousCalls = calls;
        await assert.rejects(run(options), { code: 'EEXIST' });
        assert.equal(calls, previousCalls);
      }
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });
}
