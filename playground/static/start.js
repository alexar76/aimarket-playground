(() => {
  'use strict';
  const i18n = globalThis.PlaygroundI18n;
  const $ = selector => document.querySelector(selector);
  const params = new URLSearchParams(location.search);
  let role = params.get('role') === 'consumer' ? 'consumer' : 'provider';
  let stack = params.get('stack') === 'typescript' ? 'typescript' : 'python';
  let catalog;
  let failed = false;
  let downloading = false;
  let notice = '';
  let copyNotice = '';
  const t = key => i18n.t(`start.${key}`);
  const localized = path => `${path}?lang=${i18n.currentLang()}`;
  const selected = () => catalog?.kits[`${role}-${stack}`];

  function render() {
    const entry = selected();
    document.title = `AIMarket | ${t('title')}`;
    const url = new URL(location.href);
    url.searchParams.set('role', role);
    url.searchParams.set('stack', stack);
    history.replaceState(null, '', url);
    document.querySelectorAll('[data-role]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.role === role)));
    document.querySelectorAll('[data-stack]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.stack === stack)));
    document.querySelectorAll('[data-local-link]').forEach(link => { link.href = localized(new URL(link.href).pathname); });
    $('#role-title').textContent = t(role);
    $('#role-summary').textContent = t(`${role}.summary`);
    $('#kit-name').textContent = `${role} / ${stack}`;
    $('#requirements').textContent = entry?.requirements ?? '';
    $('#checksum').textContent = entry?.sha256 ?? '';
    $('#download').disabled = !entry || downloading;
    $('#download-status').textContent = notice ? t(notice) : '';
    $('#copy-status').textContent = copyNotice ? i18n.t(copyNotice) : '';
    $('#load-status').hidden = Boolean(entry);
    $('#load-status').textContent = t(failed ? 'failed' : 'loading');
    $('#kit-files').replaceChildren(...(entry?.files ?? []).map(name => {
      const item = document.createElement('li');
      item.textContent = name;
      return item;
    }));
    document.querySelectorAll('.start-step').forEach((section, index) => {
      section.querySelector('h2').textContent = t(`${role}.step${index + 1}`);
      section.querySelector('p').textContent = t(`${role}.note${index + 1}`);
      section.querySelector('code').textContent = entry?.commands[index] ?? '';
      section.querySelector('button').disabled = !entry;
      section.querySelector('button').title = t('copy');
    });
    $('#next-link').textContent = t(`${role}.next`);
    $('#next-link').href = localized(role === 'provider' ? '/connect' : '/');
    $('#after-title').textContent = t(`${role}.after`);
    $('#after-note').textContent = t(`${role}.afterNote`);
    $('#after-link').textContent = role === 'provider' ? i18n.t('publish.link') : i18n.t('publish.account');
    $('#after-link').href = localized(role === 'provider' ? '/publish' : 'https://modelmarket.dev/start');
    $('#scope').textContent = t(`${role}.scope`);
  }

  document.querySelectorAll('[data-role], [data-stack]').forEach(button => button.addEventListener('click', () => {
    role = button.dataset.role ?? role;
    stack = button.dataset.stack ?? stack;
    notice = '';
    copyNotice = '';
    render();
  }));
  document.querySelectorAll('[data-copy-step]').forEach(button => button.addEventListener('click', async () => {
    const command = selected()?.commands[Number(button.dataset.copyStep)];
    if (!command) return;
    try {
      await navigator.clipboard.writeText(command);
      copyNotice = 'copy.copied';
    } catch (_) {
      copyNotice = 'copy.failed';
    }
    render();
  }));
  $('#download').addEventListener('click', async () => {
    const entry = selected();
    if (!entry || downloading) return;
    const key = `${role}-${stack}`;
    downloading = true;
    notice = 'downloadBusy';
    render();
    try {
      const response = await fetch(entry.url, { signal: AbortSignal.timeout(30_000) });
      if (!response.ok) throw new Error('download');
      const bytes = await response.arrayBuffer();
      const digest = await crypto.subtle.digest('SHA-256', bytes);
      const hash = Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, '0')).join('');
      if (bytes.byteLength !== entry.bytes || hash !== entry.sha256) throw new Error('checksum');
      const url = URL.createObjectURL(new Blob([bytes], { type: 'application/zip' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `${key}.zip`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
      if (`${role}-${stack}` === key) notice = 'downloaded';
    } catch (_) {
      if (`${role}-${stack}` === key) notice = 'downloadFailed';
    } finally {
      downloading = false;
      render();
    }
  });
  i18n.onChange(render);
  i18n.ready.then(async () => {
    render();
    try {
      const response = await fetch('/starters/catalog.json', { signal: AbortSignal.timeout(15_000) });
      if (!response.ok) throw new Error('catalog');
      catalog = await response.json();
      for (const key of ['provider-python', 'provider-typescript', 'consumer-python', 'consumer-typescript']) {
        const entry = catalog.kits?.[key];
        if (entry?.url !== `/starters/${key}.zip` || !/^[a-f0-9]{64}$/.test(entry.sha256)
          || !Number.isSafeInteger(entry.bytes) || entry.bytes <= 0 || entry.bytes > 2_000_000
          || !Array.isArray(entry.commands) || entry.commands.length !== 3 || !Array.isArray(entry.files)) {
          throw new Error('catalog');
        }
      }
    } catch (_) {
      catalog = null;
      failed = true;
    }
    render();
  });
})();
