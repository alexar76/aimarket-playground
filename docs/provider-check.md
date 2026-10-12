# Connect your provider

The Playground serves `/connect`: a self-service check of a developer's own
capability endpoint. It does not publish a capability or require an operator token,
wallet, stake, Hub account, or payment channel.

Use a test deployment and harmless input. This is one real POST to your provider;
the provider's own work can still cost money or have side effects. The request
carries `X-AIMarket-Test-Mode: provider-invoke-v1`. That header is informational,
not a substitute for a provider's authorization or a guarantee of a free call.

## Browser workflow

1. Run the Playground and open `/connect`. Import your configured `capability.json`
   and enter an input object satisfying its `input_schema`.
2. Confirm endpoint ownership and consent to one real invoke. Prepare the connection.
3. Publish the returned JSON at the displayed same-origin address:
   `https://your-provider.example/.well-known/aimarket-provider-check.json`.
   The challenge expires after 15 minutes and is bound to this browser session,
   manifest and input. At most three ownership attempts are allowed.
4. Select **Verify & invoke**. Download the report, including the provider-signed
   envelope, its Ed25519 signature and public key.

New `create-aimarket-agent` Python and TypeScript providers expose the proof route
when `AIMARKET_ONBOARDING_CHALLENGE` contains the issued 64-character token. Set that
environment variable and restart your test provider. Without a valid token, the
route returns 404. Remove the variable after checking. Existing services can serve
the downloaded JSON as a static file at the same path.

Only public HTTPS endpoints on port 443 are accepted by the browser service.
All resolved addresses must be public; proof and invoke connect to the same pinned
IP with the original TLS hostname. Private networks, redirects, proxies from the
environment, compressed replies and responses above 64 KiB are refused.

The invoke is never retried automatically. Repeating the run request for the same
challenge returns its cached result, including failures after dispatch. A new
challenge is an explicit new call. If a connection breaks, retry the same challenge
before preparing a new one. Challenges and reports are held in process memory for
15 minutes; restarting loses them. Use **one ASGI worker**, with edge rate limiting,
until shared durable challenge storage is introduced. No public report registry is
created; reports are returned only to the session that prepared them.

The service permits four concurrent checks and stores at most 250 challenges.
Challenge creation and uncached run attempts share hourly limits of 20 per visitor,
60 per source IP and 500 per process. Behind a proxy, configure trusted proxy
headers explicitly so source limits reflect the intended client boundary.

## Local development and CI

Install this checkout (the new CLI is not assumed to be published to PyPI):

```bash
cd aimarket-playground
uv sync --extra dev
uv run aimarket-provider-check ../my-agent/capability.json \
  --input ../my-agent/test-input.json --allow-loopback > report.json
```

Or install the package with `pip install ./aimarket-playground`, then invoke
`aimarket-provider-check capability.json --input test-input.json`.

The input file contains a JSON object, for example `{}` for an unchanged generated
provider. The CLI runs the same manifest, invoke, schema and signature checks,
prints JSON to stdout, and exits 0 on pass or 1 on failure. The CLI does **not**
claim endpoint ownership: its user explicitly selects the target on their machine.
`--allow-loopback` permits loopback development only, not arbitrary private networks;
it is never enabled by the public API.

For CI, start your provider in the job and run the command against localhost.
Archive `report.json` as a job artifact even on failure. Reports include provider
results, so use non-sensitive fixtures and apply appropriate artifact visibility.

## Versioned profile: `aimarket-provider-invoke/1`

The profile checks:

- Required provider identity, endpoint, public key, price and manifest fields.
- Input and output against a bounded JSON Schema 2020-12 subset.
- Exactly one HTTP 200 invoke response with `success: true` and an object `result`.
- `X-Provider-Signature` against the manifest's Ed25519 key and the envelope below.
- Endpoint control in browser runs only, using the same-origin challenge.

```json
{
  "capability_id": "my-agent.invoke@v1",
  "product_id": "my-agent",
  "input_sha256": "<sha256 of canonical input JSON>",
  "result": {}
}
```

Canonical JSON matches the existing Python provider: sorted keys, compact
separators, UTF-8 with unescaped Unicode, finite numbers. The signed envelope and
signature in the report can be independently checked against a separately trusted
provider public key. A key submitted by a developer proves internal consistency,
not the real-world identity or reputation of that developer. The report itself
is not signed by the Hub or a certificate authority. `checked_at` is the checker
timestamp, not a timestamp attested by the provider. Identical inputs and results
can produce identical signatures; this profile does not prove freshness.

For Python/TypeScript interoperability, use integers in signed input and output.
The existing provider contract does not normalize numeric representations across
languages (`1.0` versus `1`); floating-point values may therefore fail signature
verification. The checker does not silently rewrite the signed payload.

Supported schema keywords: `$schema`, `title`, `description`, `type`, `properties`,
`required`, `additionalProperties`, `items`, `enum`, `const`, `minimum`, `maximum`,
`exclusiveMinimum`, `exclusiveMaximum`, `minLength`, `maxLength`, `minItems`,
`maxItems`, `minProperties`, `maxProperties`. Other keywords fail explicitly.
References, regular expressions and schema composition are not accepted in this
bounded public profile. JSON documents are limited to 64 KiB, depth 16 and 4096
nodes; duplicate keys, non-finite numbers and malformed UTF-8 are rejected.

**Passing means this one provider invoke profile passed.** It does not establish
whole-protocol conformance or certification, public listing, federation, Hub
receipts, payment correctness, replay protection, availability under load or
compatibility with every implementation. These exclusions are in each complete
report as `not_tested`, consistent with the protocol's governance policy.

After a pass, continue with provider publishing or joining the federation in the
ecosystem's provider onboarding guide. Production admission remains a separate step.
