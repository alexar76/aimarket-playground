// Run against a local Playground: node tests/connect.browser.cjs
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const vm = require("node:vm");

const languages = ["en", "ru", "es", "fr", "zh"];
async function sharedStyles(page, selectors) {
  return page.evaluate((values) => Object.fromEntries(values.map((selector) => {
    const node = document.querySelector(selector);
    if (!node) throw new Error(`Missing shared component: ${selector}`);
    const style = getComputedStyle(node);
    return [selector, Object.fromEntries(["background", "borderColor", "boxShadow", "fontFamily", "backgroundSize"].map(key => [key, style[key]]))];
  })), selectors);
}
async function selectLanguage(page, lang) {
  await page.locator(`[data-lang="${lang}"]`).click();
  await page.waitForFunction((value) => document.documentElement.lang === value, lang);
  assert.equal(await page.locator(`[data-lang="${lang}"]`).getAttribute("aria-pressed"), "true");
}

async function assertLayout(page, viewport, lang) {
  const layout = await page.evaluate(() => {
    const brand = document.querySelector(".brand").getBoundingClientRect();
    const switcher = document.querySelector(".language-switcher").getBoundingClientRect();
    return {
      overflow: document.documentElement.scrollWidth > innerWidth,
      overlap: brand.left < switcher.right && brand.right > switcher.left && brand.top < switcher.bottom && brand.bottom > switcher.top,
      background: getComputedStyle(document.body).backgroundColor,
      selected: getComputedStyle(document.querySelector('[data-lang][aria-pressed="true"]')).color,
    };
  });
  assert.equal(layout.overflow, false, `${lang} overflow at ${viewport.width}`);
  assert.equal(layout.overlap, false, `${lang} navigation overlap at ${viewport.width}`);
  assert.equal(layout.background, "rgb(6, 9, 20)");
  assert.equal(layout.selected, "rgb(114, 229, 255)");
}

const manifest = {
  product_id: "browser-check", capability_id: "browser-check.invoke@v1", publisher_id: "community",
  name: "Browser check", invoke_url: "https://provider.example/invoke", price_per_call_usd: 0,
  provider_pubkey: Buffer.alloc(32, 1).toString("base64"),
  input_schema: {type:"object"}, output_schema: {type:"object"}
};

(async () => {
  const source = await fs.readFile(path.join(__dirname, "../playground/static/connect.js"), "utf8");
  const dictionarySource = source.slice(source.indexOf("const messages =") + "const messages =".length, source.indexOf("  const $ ="));
  const messages = vm.runInNewContext(`(${dictionarySource.trim().replace(/;$/, "")})`);
  for (const lang of languages) {
    assert.deepEqual(Object.keys(messages[lang]).sort(), Object.keys(messages.en).sort());
    assert.ok(Object.values(messages[lang]).every((value) => typeof value === "string" && value.trim()));
  }
  assert.match(messages.ru.title, /поставщик/);
  assert.match(messages.ru.ownership, /эндпоинт/);
  assert.match(messages.fr.manifestNote, /point de terminaison \(endpoint\)/i);
  const artifacts = await fs.mkdtemp(path.join(os.tmpdir(), "aimarket-connect-browser-"));
  const browser = await chromium.launch({headless:true});
  try {
    for (const viewport of [{width:1440,height:1000}, {width:390,height:844}, {width:320,height:740}]) {
      const page = await browser.newPage({viewport, acceptDownloads:true});
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto("http://127.0.0.1:8075/?lang=ru");
      await page.waitForFunction(() => document.documentElement.lang === "ru");
      const shared = [".scene", ".scene-grid", ".noise", ".nav", ".command-card"];
      const reference = await sharedStyles(page, [...shared, ".workspace", ".console-head", ".radar"]);
      await page.locator(".workspace").scrollIntoViewIfNeeded();
      await page.screenshot({path:path.join(artifacts, `reference-${viewport.width}.png`)});
      await page.goto("http://127.0.0.1:8075/connect?lang=ru");
      await page.waitForFunction(() => document.title.includes("Подключить"));
      assert.deepEqual(await sharedStyles(page, [...shared, ".workspace", ".console-head", ".radar"]), reference);
      assert.equal(await page.locator(".radar i").evaluate(node => getComputedStyle(node).animationName), "spin");
      await page.screenshot({path:path.join(artifacts, `initial-${viewport.width}.png`), fullPage:true});
      await page.locator("#manifest").fill(JSON.stringify(manifest, null, 2));
      await page.locator("#consent").check();
      await page.locator("#prepare").click();
      await page.locator("#proof-panel").waitFor({state:"visible"});
      assert.equal(await page.locator("#proof-url").textContent(), "https://provider.example/.well-known/aimarket-provider-check.json");
      const proofDownload = page.waitForEvent("download");
      await page.locator("#download-proof").click();
      assert.equal((await proofDownload).suggestedFilename(), "aimarket-provider-check.json");
      // UI state fixtures only; real cryptographic/network checks live in Python tests.
      let attempts = 0;
      await page.route("**/api/provider-check/challenges/*/run", (route) => {
        attempts++;
        if (attempts === 1) return route.fulfill({status:422, contentType:"application/json", body:JSON.stringify({detail:"Ownership proof missing <img src=x onerror=alert(1)>"})});
        return route.fulfill({status:200, contentType:"application/json", body:JSON.stringify({
          profile:"aimarket-provider-invoke/1", status:"passed", checks:[
            {id:"endpoint_control",status:"passed"},{id:"manifest",status:"passed"},
            {id:"invoke",status:"passed"},{id:"output_schema",status:"passed"},{id:"provider_signature",status:"passed"}
          ], evidence:{fixture:"UI state only"}
        })});
      });
      await page.locator("#run-check").click();
      await page.locator("#error").waitFor({state:"visible"});
      assert.equal(await page.locator("#error img").count(), 0);
      await page.locator("#run-check").click();
      await page.locator("#report-panel").waitFor({state:"visible"});
      assert.equal(await page.locator("#checks li").count(), 5);
      const reportDownload = page.waitForEvent("download");
      await page.locator("#download-report").click();
      assert.equal((await reportDownload).suggestedFilename(), "aimarket-provider-report.json");
      for (const lang of languages) {
        await selectLanguage(page, lang);
        assert.equal(await page.locator("html").getAttribute("lang"), lang);
        await assertLayout(page, viewport, lang);
        const overlap = await page.evaluate(() => {
          const title = document.querySelector("h1").getBoundingClientRect();
          const tag = document.querySelector(".tag").getBoundingClientRect();
          return title.left < tag.right && title.right > tag.left && title.top < tag.bottom && title.bottom > tag.top;
        });
        assert.equal(overlap, false, `${lang} header overlap`);
      }
      await selectLanguage(page, "ru");
      await page.screenshot({path:path.join(artifacts, `report-${viewport.width}.png`), fullPage:true});
      await page.locator("#invoke-input").fill('{"changed":true}');
      assert.equal(await page.locator("#report-panel").isVisible(), false);
      assert.equal(await page.locator("#proof-panel").isVisible(), false);
      assert.deepEqual(errors, []);
      await page.locator("#guide-link").click();
      await page.waitForURL("**/connect/guide?lang=ru");
      await page.locator("#guide-ru").waitFor({state:"visible"});
      assert.deepEqual(await sharedStyles(page, shared), Object.fromEntries(shared.map(selector => [selector, reference[selector]])));
      assert.equal(await page.locator("#guide-en").isVisible(), false);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.screenshot({path:path.join(artifacts, `guide-${viewport.width}.png`), fullPage:true});
      for (const lang of languages) {
        await selectLanguage(page, lang);
        await page.locator(`#guide-${lang}`).waitFor({state:"visible"});
        assert.equal(await page.locator(".guide article:visible").count(), 1);
        assert.equal(await page.locator(`#guide-${lang} h2`).count(), 6);
        assert.equal(await page.title(), `AIMarket | ${await page.locator(`#guide-${lang} h1`).textContent()}`);
        await assertLayout(page, viewport, lang);
        await page.screenshot({path:path.join(artifacts, `guide-${lang}-${viewport.width}.png`), fullPage:true});
        await page.locator(`#guide-${lang} a`).first().click();
        await page.waitForFunction((value) => document.documentElement.lang === value && !!document.querySelector("#guide-link"), lang);
        assert.equal(await page.locator("h1").textContent(), messages[lang].title);
        await page.locator("#guide-link").click();
        await page.locator(`#guide-${lang}`).waitFor({state:"visible"});
      }
      // No query parameter: the shared language choice survives navigation and reloads.
      await page.locator(".brand").click();
      await page.waitForFunction(() => document.documentElement.lang === "zh");
      await page.goto("http://127.0.0.1:8075/connect");
      await page.waitForFunction(() => document.documentElement.lang === "zh");
      await page.reload();
      await page.waitForFunction(() => document.documentElement.lang === "zh");
      await page.goto("http://127.0.0.1:8075/connect/guide?lang=es");
      await page.locator("#guide-es").waitFor({state:"visible"});
      assert.deepEqual(errors, []);
      await page.close();
    }
    console.log(JSON.stringify({status:"passed", viewports:[1440,390,320], languages:5, artifacts}));
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
