// BASE_URL may point to production; this suite never invokes a service or pays.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8075';
const languages = ['en', 'ru', 'es', 'fr', 'zh'];

async function styles(page) {
  return page.evaluate(() => Object.fromEntries(['.scene', '.scene-grid', '.noise', '.nav', '.workspace', '.console-head', '.command-card'].map(selector => {
    const style = getComputedStyle(document.querySelector(selector));
    return [selector, [style.background, style.borderColor, style.boxShadow, style.fontFamily]];
  })));
}

(async () => {
  const artifacts = await fs.mkdtemp(path.join(os.tmpdir(), 'aimarket-start-browser-'));
  const browser = await chromium.launch({ headless: true });
  let downloads = 0;
  try {
    for (const width of [1440, 768, 390, 320]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, acceptDownloads: true,
        permissions: ['clipboard-read', 'clipboard-write'], reducedMotion: 'reduce' });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(`${BASE}/?lang=en`);
      const reference = await styles(page);
      await page.goto(`${BASE}/start?lang=ru`);
      await page.waitForFunction(() => !document.querySelector('#download').disabled);
      assert.deepEqual(await styles(page), reference);
      const catalog = await page.request.get(`${BASE}/starters/catalog.json`).then(response => response.json());
      for (const role of ['provider', 'consumer']) {
        await page.locator(`[data-role="${role}"]`).click();
        for (const stack of ['python', 'typescript']) {
          await page.locator(`[data-stack="${stack}"]`).click();
          const key = `${role}-${stack}`;
          assert.deepEqual(await page.locator('.start-step code').allTextContents(), catalog.kits[key].commands);
          assert.equal(await page.locator('#requirements').textContent(), catalog.kits[key].requirements);
          for (const lang of languages) {
            await page.locator(`[data-lang="${lang}"]`).click();
            await page.waitForFunction(value => document.documentElement.lang === value, lang);
            const messages = await page.request.get(`${BASE}/locales/${lang}.json`).then(response => response.json());
            assert.equal(await page.locator('#role-title').textContent(), messages[`start.${role}`]);
            assert.equal(await page.locator('#scope').textContent(), messages[`start.${role}.scope`]);
            const layout = await page.evaluate(() => {
              const brand = document.querySelector('.brand').getBoundingClientRect();
              const languages = document.querySelector('.language-switcher').getBoundingClientRect();
              return {
                overflow: document.documentElement.scrollWidth > innerWidth,
                escaped: [...document.querySelectorAll('.start-main h1, .start-main h2, .start-main p, .segments, .command-card, #download')].some(node => {
                  const box = node.getBoundingClientRect();
                  return box.right > innerWidth + 1 || box.left < -1 || node.scrollWidth > node.clientWidth + 1;
                }),
                overlap: brand.left < languages.right && brand.right > languages.left && brand.top < languages.bottom && brand.bottom > languages.top,
              };
            });
            assert.deepEqual(layout, { overflow: false, escaped: false, overlap: false }, `${key} ${lang} ${width}`);
            assert.ok((await page.locator('#next-link').getAttribute('href')).endsWith(`lang=${lang}`));
          }
          if (width === 1440) {
            const download = page.waitForEvent('download');
            await page.locator('#download').click();
            const file = await download;
            assert.equal(file.suggestedFilename(), `${key}.zip`);
            const bytes = await fs.readFile(await file.path());
            assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), catalog.kits[key].sha256);
            downloads++;
            await page.locator('[data-copy-step="0"]').click();
            assert.equal(await page.evaluate(() => navigator.clipboard.readText()), catalog.kits[key].commands[0]);
          }
        }
        await page.locator('[data-lang="ru"]').click();
      await page.waitForFunction(() => document.documentElement.lang === 'ru');
        if (width === 1440) {
          const messages = await page.request.get(`${BASE}/locales/ru.json`).then(response => response.json());
          assert.equal(await page.locator('#copy-status').textContent(), messages['copy.copied']);
        }
        await page.screenshot({ path: path.join(artifacts, `${role}-${width}.png`), fullPage: true });
      }
      await page.reload();
      await page.waitForFunction(() => !document.querySelector('#download').disabled);
      assert.equal(await page.locator('[data-role="consumer"]').getAttribute('aria-pressed'), 'true');
      assert.equal(await page.locator('[data-stack="typescript"]').getAttribute('aria-pressed'), 'true');
      assert.equal(await page.locator('html').getAttribute('lang'), 'ru');
      assert.deepEqual(errors, []);
      await context.close();
    }
    // Fail closed if CDN/cache returns an archive that does not match this catalog.
    const page = await browser.newPage();
    await page.route('**/starters/provider-python.zip', route => route.fulfill({ status: 200, body: 'tampered' }));
    let unexpectedDownload = false;
    page.on('download', () => { unexpectedDownload = true; });
    await page.goto(`${BASE}/start?lang=en`);
    await page.waitForFunction(() => !document.querySelector('#download').disabled);
    await page.locator('#download').click();
    await page.waitForFunction(() => document.querySelector('#download-status').textContent.includes('failed'));
    assert.equal(unexpectedDownload, false);
    await page.route('**/starters/catalog.json', route => route.fulfill({ status: 503, body: '{}' }));
    await page.reload();
    await page.waitForFunction(() => document.querySelector('#load-status').textContent.includes('could not'));
    assert.equal(await page.locator('#download').isDisabled(), true);
    await page.close();
    console.log(JSON.stringify({ status: 'passed', combinations: 80, downloads, artifacts }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
