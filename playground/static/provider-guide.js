(() => {
  "use strict";
  const i18n = globalThis.PlaygroundI18n;
  function language() {
    const lang = i18n.currentLang();
    document.querySelectorAll(".guide article").forEach((article) => {
      article.hidden = article.lang !== lang;
    });
    document.title = `AIMarket | ${document.querySelector(`#guide-${lang} h1`).textContent}`;
    document.getElementById("connect-link").href = `/connect?lang=${lang}`;
  }
  i18n.onChange(language);
  i18n.ready.then(language);
})();
