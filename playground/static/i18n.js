(() => {
  "use strict";
  const LOCALES = ["en", "ru", "es", "fr", "zh"];
  const STORAGE_KEY = "aimarket-portal-lang";
  const VERSION = "20260820c";
  const cache = Object.create(null);
  const listeners = new Set();
  let current = "en";
  let dictionary = null;

  function detect() {
    const query = new URLSearchParams(location.search).get("lang");
    if (LOCALES.includes(query)) return query;
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (LOCALES.includes(stored)) return stored;
    } catch (_) {}
    const browser = (navigator.language || "en").toLowerCase();
    return LOCALES.find((lang) => browser.startsWith(lang)) || "en";
  }

  async function load(lang) {
    if (cache[lang]) return cache[lang];
    const response = await fetch(`/locales/${lang}.json?v=${VERSION}`);
    if (!response.ok) throw new Error(`locale ${lang}: ${response.status}`);
    cache[lang] = await response.json();
    return cache[lang];
  }

  function t(key, fallback = key) {
    return dictionary?.[key] ?? fallback;
  }

  function apply() {
    if (!dictionary) return;
    document.querySelectorAll("[data-i18n]").forEach((element) => {
      const value = dictionary[element.dataset.i18n];
      if (value != null) element.textContent = value;
    });
    document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
      const value = dictionary[element.dataset.i18nAriaLabel];
      if (value != null) element.setAttribute("aria-label", value);
    });
    document.documentElement.lang = current;
    document.title = t("meta.title", document.title);
    const meta = document.querySelector('meta[name="description"]');
    if (meta) meta.content = t("meta.description", meta.content);
    document.querySelectorAll("[data-lang]").forEach((button) => {
      button.setAttribute("aria-pressed", button.dataset.lang === current ? "true" : "false");
    });
  }

  async function setLang(lang) {
    if (!LOCALES.includes(lang)) lang = "en";
    try {
      dictionary = await load(lang);
      current = lang;
    } catch (error) {
      if (lang !== "en") {
        dictionary = await load("en");
        current = "en";
      } else {
        throw error;
      }
    }
    apply();
    try { localStorage.setItem(STORAGE_KEY, current); } catch (_) {}
    const url = new URL(location.href);
    if (current === "en") url.searchParams.delete("lang");
    else url.searchParams.set("lang", current);
    history.replaceState(null, "", url);
    listeners.forEach((listener) => listener(current));
  }

  document.querySelectorAll("[data-lang]").forEach((button) => {
    button.addEventListener("click", () => setLang(button.dataset.lang).catch(() => {}));
  });

  globalThis.PlaygroundI18n = {
    t,
    currentLang: () => current,
    onChange(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    ready: setLang(detect()),
    setLang,
  };
})();
