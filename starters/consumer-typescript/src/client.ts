import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { market } from './sdk/market';
import type { SearchResponse } from './sdk/models';

export const HUB = 'https://modelmarket.dev';
export const PRODUCT = 'gaia.gateway';
export const CAPABILITY = 'gaia.weather.read@v1';
export const SOURCE = 'https://iot.modelmarket.dev';

export async function run(options: {
  invoke?: boolean; budget?: number; directory?: string; apiKey?: string; fetch?: typeof fetch;
} = {}) {
  const budget = options.budget ?? 0.01;
  if (!Number.isFinite(budget) || budget < 0 || budget > 1) throw new Error('Budget must be 0..1 USD');
  const fetchFn = options.fetch ?? fetch;
  if (!options.invoke) {
    const query = new URLSearchParams({ intent: 'GAIA weather', budget: String(budget), limit: '10' });
    const response = await fetchFn(`${HUB}/ai-market/v2/search?${query}`, {
      redirect: 'error', signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) throw new Error(`Discovery HTTP ${response.status}`);
    return response.json();
  }
  const directory = options.directory ?? '.';
  const input: unknown = JSON.parse(await readFile(join(directory, 'input.json'), 'utf8'));
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('input.json must contain an object');
  // Refuse repeat attempts even after a timeout: the first request may have been billed.
  await writeFile(join(directory, 'attempt.json'), JSON.stringify({
    attempt_id: randomUUID(), hub: HUB, max_price_usd: budget,
  }), { flag: 'wx' });
  const result = await market.run({
    intent: 'GAIA weather', input: input as Record<string, unknown>, hubUrl: HUB,
    budgetUsd: budget, receiptPolicy: 'require',
    payment: options.apiKey ? { kind: 'credits', apiKey: options.apiKey } : { kind: 'trial' },
    // This fixture belongs only to GAIA weather; never send it to a different match.
    fetch: async (url, init) => {
      const response = await fetchFn(url, init);
      if (new URL(String(url)).pathname.endsWith('/search') && response.ok) {
        const body = await response.json() as SearchResponse;
        return Response.json({ ...body, matches: (body.matches ?? []).filter(match =>
          match.product_id === PRODUCT && match.capability_id === CAPABILITY && match.source_hub === SOURCE),
        });
      }
      return response;
    },
  });
  await writeFile(join(directory, 'report.json'), JSON.stringify(result, null, 2));
  if (!result.trusted || result.invocation.success !== true) throw new Error('Invocation or receipt verification failed');
  const receipt = result.invocation.receipt;
  const price = receipt?.price_usd;
  if (receipt?.product_id !== PRODUCT || receipt?.capability_id !== CAPABILITY || receipt?.success !== true
    || typeof price !== 'number' || !Number.isFinite(price) || price < 0 || price > budget) {
    throw new Error('Receipt does not match this successful, price-capped invocation');
  }
  return result;
}
